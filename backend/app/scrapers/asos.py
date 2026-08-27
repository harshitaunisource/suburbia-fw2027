"""
ASOS scraper.

STATUS: the strongest-evidence competitor scraper in this project after
Suburbia/Old Navy/C&A -- a prior live run against
https://www.asos.com/us/women/jumpers-cardigans/cat/?cid=2637 style
category URLs successfully returned 71 real products with correct name,
URL, product code, image, and description. The one confirmed live bug
was price=None across the board, traced to a fixed "first 2000
characters of the page" scan window missing the price entirely (ASOS
has a large nav/header block before the actual product price text).
Fixed here by anchoring the price search near the product name instead
(see app/scrapers/_price_utils.py), with a full-page fallback scan.

STRUCTURE (confirmed live):
  Product URL pattern: https://www.asos.com/us/<brand-slug>/<name-slug>/prd/<id>
  og:title / og:image / og:description all present and reliable.
  Category page: plain <a href="...prd/<id>..."> links present in
  server-rendered HTML (no Playwright strictly required for discovery,
  but kept on Playwright here since ASOS lazy-loads additional products
  on scroll, confirmed via "Scraped 71 products" needing scroll to reach
  that count).

NOT YET CONFIRMED: sizes, colors, material as distinct structured
fields; multi-page/currency handling for non-MXN storefronts (ASOS's US
site returns USD -- see CURRENCY note below).
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

BASE_URL = "https://www.asos.com"
PDP_LINK_RE = re.compile(r"/us/[a-z0-9\-]+/[a-z0-9\-]+/prd/(\d+)")

CATEGORY_MAP = {
    "jumper": "sweaters",
    "cardigan": "sweaters",
    "sweater": "sweaters",
    "knitwear": "sweaters",
    "blouse": "blouses",
    "shirt": "blouses",
}

# ASOS's .com/us storefront prices in USD, not MXN -- do not silently
# relabel these as MXN (that was a real bug: the first working run
# tagged everything currency='MXN' while the values were actually USD).
CURRENCY = "USD"


class AsosScraper(PlaywrightScraper):
    source_name = "asos"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)
        print(f"[asos] fetching category page: {url}", flush=True)
        html = self.get_rendered_html(url, wait_ms=3000, scroll=True)

        ids = sorted(set(PDP_LINK_RE.findall(html)))
        # PDP_LINK_RE captures only the id group; rebuild full hrefs by
        # re-matching with the full path this time.
        full_paths = sorted(set(re.findall(r"/us/[a-z0-9\-]+/[a-z0-9\-]+/prd/\d+", html)))
        product_urls = [urljoin(BASE_URL, p) for p in full_paths] or [
            f"{BASE_URL}/us/prd/{pid}" for pid in ids
        ]

        if not product_urls:
            raise ScraperError(
                f"No product links found on {url}. ASOS's link structure "
                "may have changed, or the page didn't fully render before "
                "scraping. Not fabricating data."
            )

        # PROGRESS LOGGING: ASOS categories commonly run 50-100+ products,
        # each requiring its own real page navigation -- with no output at
        # all, a run in progress is indistinguishable from a hang. Every
        # product prints a line as soon as it's done.
        total = len(product_urls)
        print(f"[asos] found {total} product URLs -- scraping each one now...", flush=True)

        products: list[ScrapedProduct] = []
        for i, purl in enumerate(product_urls, start=1):
            try:
                product = self.scrape_product(purl, category_hint=category)
                products.append(product)
                print(f"[asos] ({i}/{total}) OK: {product.product_name}", flush=True)
            except ScraperError as e:
                print(f"[asos] ({i}/{total}) SKIP: {purl} -- {e}", flush=True)
                continue
            except Exception as e:
                print(f"[asos] ({i}/{total}) SKIP (unexpected): {purl} -- {e}", flush=True)
                continue
        print(f"[asos] done -- {len(products)}/{total} products scraped successfully.", flush=True)
        return products

    def scrape_product(self, url: str, category_hint: Optional[str] = None) -> ScrapedProduct:
        html = self.get_rendered_html(url, wait_selector="h1", wait_ms=1500)
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        raw_title = meta_content(soup, "og:title")
        name = clean_title(raw_title, separators=(" | ASOS",))
        if not name:
            raise ScraperError(f"Could not find product name for {url}")

        main_image = meta_content(soup, "og:image")
        description = meta_content(soup, "og:description")

        # Fix for the confirmed live bug: anchor the price scan near the
        # product name instead of a fixed leading window, which missed
        # the price entirely on ASOS's nav/header-heavy pages.
        prices = extract_prices_near(text, anchor=name[:30], window=1500)
        price, original_price = current_and_original(prices)
        disc_pct = discount_percentage(price, original_price)

        m = re.search(r"/prd/(\d+)", url)
        product_code = m.group(1) if m else None

        category = category_hint or self._category_from_url(url) or self._category_from_name(name)

        return ScrapedProduct(
            source=self.source_name,
            brand=None,  # ASOS is a multi-brand marketplace; brand is the first URL slug (approximate)
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
    def _category_from_url(url: str) -> Optional[str]:
        lower = url.lower()
        for k, v in CATEGORY_MAP.items():
            if k in lower:
                return v
        return None

    @staticmethod
    def _category_from_name(name: str) -> str:
        lower = name.lower()
        for k, v in CATEGORY_MAP.items():
            if k in lower:
                return v
        return "unknown"


if __name__ == "__main__":
    # Manual smoke test -- run from a machine with real internet access:
    #   cd backend && python -m app.scrapers.asos
    scraper = AsosScraper(headless=True)
    try:
        products = scraper.scrape_category(
            "https://www.asos.com/us/women/jumpers-cardigans/cat/?cid=2637", max_pages=1
        )
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()