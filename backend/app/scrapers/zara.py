"""
Zara Mexico scraper.

CONFIRMED LIVE FINDING (see zara_category.html / zara_product.html
captured in this project's history): both the category and product URLs
return an Akamai Bot Manager "interstitial" challenge page -- not a plain
403, but an HTML shell containing a proof-of-work JavaScript challenge
(`bm-verify` token + a `pow` value the page computes and POSTs back
before being allowed through, then a 5-second meta-refresh redirect).

This is a materially harder block than H&M's (a static 403) or
Suburbia's (none): it requires actually executing Akamai's challenge
script and completing a real page lifecycle, which a plain httpx client
cannot do at all. A real Playwright/Chrome browser executes JavaScript
and may complete the challenge on its own (that's what the challenge is
designed to allow for genuine browsers) -- but there is no guarantee,
since Akamai also fingerprints headless/automated browser signals.

This project intentionally does NOT attempt to reverse-engineer or
solve the proof-of-work token by hand -- that would mean purpose-built
code to defeat a live anti-bot/security system, which is out of scope
here regardless of outcome. What this scraper does instead:
  - Navigates with a real browser and gives Akamai's own challenge script
    a chance to run and resolve itself (often enough for a real browser).
  - Waits for actual product content to appear (wait_selector) rather
    than assuming the redirect succeeded.
  - If product content never appears, raises ScraperError cleanly
    instead of scraping/returning the interstitial shell as if it were
    real data (which is exactly the bug that crashed this scraper live
    last time -- IndexError from treating the challenge page's text as
    if it contained a price).

If this keeps failing in your environment, Zara's data for this project
will need to come from a different acquisition path entirely (e.g. a
paid retail-data provider, or manual sampling) -- that is a legitimate
and expected outcome for a site this aggressively protected, not a bug
to keep patching.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.scrapers._generic_playwright_template import clean_title, meta_content
from app.scrapers._price_utils import current_and_original, discount_percentage, extract_prices_near
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

BASE_URL = "https://www.zara.com"
# Generalized to any two-letter/two-letter locale (was hardcoded to
# /mx/es/ only, which matched zero products against the real,
# user-confirmed India-store URL https://www.zara.com/in/en/... below).
PDP_LINK_RE = re.compile(r"/[a-z]{2}/[a-z]{2}/[a-z0-9\-]+-p\d+\.html")

# Real, user-confirmed category URLs (2026-08-26):
CATEGORY_URL_SWEATERS = "https://www.zara.com/in/en/woman-knitwear-l1152.html"
CATEGORY_URL_BLOUSES = "https://www.zara.com/in/en/woman-shirts-blouses-l1221.html"

# The confirmed working URLs are on Zara's India storefront (/in/en/),
# which prices in INR, not MXN -- do not silently mislabel these (same
# class of bug already fixed once on ASOS, which priced in USD).
CURRENCY = "INR"

CATEGORY_MAP = {
    "punto": "sweaters",  # "mujer-punto" = women's knitwear (MX/ES locale)
    "sueter": "sweaters",
    "knitwear": "sweaters",  # English locale (e.g. India store)
    "camisas-blusas": "blouses",
    "blusas": "blouses",
    "shirts-blouses": "blouses",  # English locale
}


class ZaraScraper(PlaywrightScraper):
    source_name = "zara"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)
        html = self.get_rendered_html(url, wait_ms=4000, scroll=True, check_blocked=False)

        if self._looks_like_challenge_page(html):
            raise ScraperError(
                f"Zara returned an Akamai bot-challenge interstitial for {url} "
                "that did not resolve within the wait window. Not attempting "
                "to solve the proof-of-work challenge (out of scope). Try a "
                "longer wait_ms, a non-headless run, or accept Zara as "
                "currently unscrapeable from this environment."
            )

        paths = sorted(set(PDP_LINK_RE.findall(html)))
        product_urls = [urljoin(BASE_URL, p) for p in paths]

        products: list[ScrapedProduct] = []
        for purl in product_urls:
            try:
                products.append(self.scrape_product(purl, category_hint=category))
            except ScraperError:
                continue
            except Exception as e:
                # Defensive catch-all: a single malformed product page must
                # never crash the whole category scrape (this is the exact
                # class of bug -- an uncaught IndexError from empty price
                # lists -- that broke this scraper live previously).
                continue
        return products

    def scrape_product(self, url: str, category_hint: Optional[str] = None) -> ScrapedProduct:
        html = self.get_rendered_html(url, wait_selector="h1", wait_ms=3000, check_blocked=False)

        if self._looks_like_challenge_page(html):
            raise ScraperError(f"Zara bot-challenge did not resolve for product page {url}.")

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        name = meta_content(soup, "og:title") or self._text_or_none(soup.select_one("h1"))
        name = clean_title(name)
        if not name:
            raise ScraperError(f"Could not find product name for {url} -- page likely did not load real content.")

        main_image = meta_content(soup, "og:image")
        description = meta_content(soup, "og:description")

        prices = extract_prices_near(text, anchor=name[:30])
        price, original_price = current_and_original(prices)
        disc_pct = discount_percentage(price, original_price)

        code_match = re.search(r"-p(\d+)\.html", url)
        product_code = code_match.group(1) if code_match else None

        category = category_hint or self._category_from_url(url)

        return ScrapedProduct(
            source=self.source_name,
            brand="Zara",
            category=category,
            subcategory=None,
            product_name=name,
            product_code=product_code,
            product_url=url,
            image_url=main_image,
            additional_image_urls=[],
            price=price,
            currency=CURRENCY,
            original_price=original_price,
            discount_price=price if original_price else None,
            discount_percentage=disc_pct,
            description=description,
            material=None,
            sizes=[],
            colors=[],
            availability="in_stock",
        )

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _looks_like_challenge_page(html: str) -> bool:
        lowered = html.lower()
        return "bm-verify" in lowered or "akam-logo" in lowered or "interstitial" in lowered

    @staticmethod
    def _category_from_url(url: str) -> str:
        lower = url.lower()
        for k, v in CATEGORY_MAP.items():
            if k in lower:
                return v
        return "unknown"

    @staticmethod
    def _text_or_none(el) -> Optional[str]:
        return el.get_text(strip=True) if el else None


if __name__ == "__main__":
    # Manual smoke test -- run from a machine with real internet access:
    #   cd backend && python -m app.scrapers.zara
    scraper = ZaraScraper(headless=False)  # non-headless gives the challenge the best chance to pass
    try:
        products = scraper.scrape_category(CATEGORY_URL_SWEATERS, max_pages=1)
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()