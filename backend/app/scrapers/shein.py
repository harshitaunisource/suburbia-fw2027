"""
SHEIN scraper.

CONFIRMED LIVE FINDING: SHEIN's category pages redirect automated
traffic to a risk/challenge page mid-navigation (confirmed live: the
page navigated away while this scraper was still scrolling, which
previously crashed with a raw `Page.evaluate: Execution context was
destroyed` Playwright error instead of a clean, understood failure).

This project does not attempt to defeat SHEIN's bot/risk challenge. This
scraper's job is to detect that block reliably and report it as a
ScraperError -- never to fabricate data, and never to crash the whole
pipeline run. See playwright_base.py's `check_blocked` / BLOCK_TEXT_MARKERS
for the shared detection logic (also handles the mid-scroll navigation
crash via a try/except around each scroll step).

If SHEIN needs to be included in the final catalogue's competitive
analysis in practice, expect to source that specific brand's assortment
data manually or via a licensed retail-data provider rather than direct
scraping -- that is a reasonable and expected outcome for a site this
aggressively protected.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

# Real, user-confirmed category URLs (2026-08-26) are on shein.com.mx
# (Mexico storefront), not us.shein.com as originally guessed. BASE_URL
# is now derived per-call from the actual category URL's own origin
# (see scrape_category) instead of being hardcoded, so this scraper
# works against whichever SHEIN regional domain it's pointed at.
CATEGORY_URL_SWEATERS = "https://www.shein.com.mx/category/Sweaters-sc-00831455.html"
CATEGORY_URL_BLOUSES = "https://www.shein.com.mx/style/Women-Blouses-sc-00122967.html"

PDP_LINK_RE = re.compile(r'href="([^"]*-p-\d+-cat-\d+\.html[^"]*)"')

CATEGORY_MAP = {
    "sweater": "sweaters",
    "cardigan": "sweaters",
    "knitwear": "sweaters",
    "blouse": "blouses",
    "shirt": "blouses",
}


class SheinScraper(PlaywrightScraper):
    source_name = "shein"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)

        # check_blocked=True (default) -- SHEIN's risk-challenge page text
        # is expected to trip BLOCK_TEXT_MARKERS and raise ScraperError
        # here rather than being scraped as if it were product data.
        html = self.get_rendered_html(url, wait_ms=4000, scroll=True)

        paths = sorted(set(PDP_LINK_RE.findall(html)))
        if not paths:
            raise ScraperError(
                f"No product links found on {url}. Either SHEIN's link "
                "structure differs from PDP_LINK_RE (unconfirmed from this "
                "sandboxed build environment), or the category rendered an "
                "empty/blocked page that didn't match a known block marker. "
                "Not fabricating data."
            )
        product_urls = [urljoin(url, p) for p in paths]

        products: list[ScrapedProduct] = []
        for purl in product_urls:
            try:
                products.append(self.scrape_product(purl, category_hint=category))
            except ScraperError:
                continue
            except Exception:
                continue
        return products

    def scrape_product(self, url: str, category_hint: Optional[str] = None) -> ScrapedProduct:
        html = self.get_rendered_html(url, wait_selector="h1", wait_ms=1500)
        return parse_generic_product(
            html, url, self.source_name, brand="SHEIN", category_hint=category_hint, currency="MXN"
        )

    @staticmethod
    def _category_from_url(url: str) -> Optional[str]:
        lower = url.lower()
        for k, v in CATEGORY_MAP.items():
            if k in lower:
                return v
        return None


if __name__ == "__main__":
    # Manual smoke test -- run from a machine with real internet access:
    #   cd backend && python -m app.scrapers.shein
    scraper = SheinScraper(headless=True)
    try:
        products = scraper.scrape_category(CATEGORY_URL_SWEATERS)
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()