"""
Target scraper.

Target does not ship to / operate in Mexico -- included per spec purely
as a competitor benchmark. Uses target.com (US site, USD prices).

STATUS: architecture-complete, NOT live-verified from the sandboxed build
environment (no internet access there). Target's site is a heavy
React/Next.js SPA behind bot-mitigation (commonly PerimeterX on
target.com), so this is built on PlaywrightScraper rather than plain
httpx from the start, using only standards-based OpenGraph parsing
(see _generic_playwright_template.py) rather than guessing Target-
specific CSS classes that would break on the next redeploy anyway.

Smoke-test before trusting: run `python -m app.scrapers.target` from a
machine with real internet access.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

BASE_URL = "https://www.target.com"
PDP_LINK_RE = re.compile(r'href="(/p/[a-z0-9\-]+/-/A-\d+[^"]*)"')

CATEGORY_MAP = {
    "sweater": "sweaters",
    "cardigan": "sweaters",
    "blouse": "blouses",
    "shirt": "blouses",
}


class TargetScraper(PlaywrightScraper):
    source_name = "target"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)
        html = self.get_rendered_html(url, wait_ms=3500, scroll=True)

        paths = sorted(set(PDP_LINK_RE.findall(html)))
        if not paths:
            raise ScraperError(
                f"No product links found on {url}. Target's PDP link pattern "
                "could not be confirmed from the sandboxed build environment. "
                "Not fabricating data -- inspect real output and tighten "
                "PDP_LINK_RE before trusting this source."
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
            html, url, self.source_name, brand="Target", category_hint=category_hint, currency="USD"
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
    #   cd backend && python -m app.scrapers.target
    scraper = TargetScraper(headless=True)
    try:
        products = scraper.scrape_category("https://www.target.com/c/women-s-sweaters/-/N-5xtdl")
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()
