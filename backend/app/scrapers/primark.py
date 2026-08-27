"""
Primark scraper.

IMPORTANT CAVEAT: Primark historically runs a very limited e-commerce
operation (traditionally store-only in most markets, with online
ordering/click-and-collect only in a subset of countries and often only
for a subset of categories). This means, unlike the other 8 competitors,
Primark may simply not have a conventional scrapeable product catalogue
with prices for women's sweaters/blouses at all -- confirm this first
(manually, in a browser) before assuming this scraper is broken if it
returns nothing.

STATUS: architecture-complete, NOT live-verified from the sandboxed
build environment (no internet access there). The category URL below is
a placeholder best-guess -- confirm Primark's real current category URL
for women's knitwear/blouses in a real browser and update CATEGORY_URL
accordingly before running this for real.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

BASE_URL = "https://www.primark.com"
# PLACEHOLDER -- confirm the real, current category URL in a browser first.
CATEGORY_URL_SWEATERS = "https://www.primark.com/en-us/c/women/clothing/sweaters-and-cardigans"
CATEGORY_URL_BLOUSES = "https://www.primark.com/en-gb/c/women/clothing/shirts-and-blouses/blouses"

PDP_LINK_RE = re.compile(r'href="(/en-[a-z]{2}/p/[a-z0-9\-]+)"')

CATEGORY_MAP = {
    "knitwear": "sweaters",
    "sweater": "sweaters",
    "jumper": "sweaters",
    "cardigan": "sweaters",
    "blouse": "blouses",
    "shirt": "blouses",
}


class PrimarkScraper(PlaywrightScraper):
    source_name = "primark"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)
        html = self.get_rendered_html(url, wait_ms=3500, scroll=True)

        paths = sorted(set(PDP_LINK_RE.findall(html)))
        if not paths:
            raise ScraperError(
                f"No product links found on {url}. This may mean (a) the "
                "PDP link pattern needs updating, or (b) Primark genuinely "
                "has no online catalogue for this category/market -- check "
                "manually in a browser first. Not fabricating data."
            )
        product_urls = [urljoin(BASE_URL, p) for p in paths]

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
            html, url, self.source_name, brand="Primark", category_hint=category_hint, currency="GBP"
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
    #   cd backend && python -m app.scrapers.primark
    scraper = PrimarkScraper(headless=True)
    try:
        products = scraper.scrape_category(CATEGORY_URL_SWEATERS)
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()
