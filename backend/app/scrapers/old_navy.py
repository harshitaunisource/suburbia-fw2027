"""
Old Navy scraper.

REWRITTEN: the real, user-confirmed category URLs (2026-08-26) are on
oldnavy.gap.com -- Old Navy's US site, part of Gap Inc's shared
e-commerce platform. This is a COMPLETELY DIFFERENT site from
oldnavy.mx (the Mexico storefront this scraper was originally built and
live-verified against): different domain, different infrastructure,
almost certainly a different DOM structure and page-text language
(English, not Spanish). Patching the old Spanish-specific parsing logic
(which anchored on words like "Cargando", "Quedan N piezas") onto an
unrelated English-language site would silently return nothing useful,
so this is a fresh build on the same generic OpenGraph-based template
used for Target/Primark/SHEIN/Boohoo, rather than a patch.

The original oldnavy.mx logic is NOT deleted from this project's history
(see git/conversation log) -- if oldnavy.mx ever becomes usable again in
the future, that version's price-extraction approach (handling prices
split across separate DOM nodes) is worth revisiting.

STATUS: architecture-complete, UNVERIFIED against real HTML (this
project's build environment has no internet access at all). Also
UNTESTED against Gap Inc's own bot-mitigation, which may or may not be
present -- Gap-family sites (Gap, Old Navy, Banana Republic, Athleta)
have historically used PerimeterX in some markets.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

# Real, user-confirmed category URLs (2026-08-26):
CATEGORY_URL_SWEATERS = "https://oldnavy.gap.com/browse/women/sweaters-and-cardigans?cid=20408#department=136"
CATEGORY_URL_BLOUSES = "https://oldnavy.gap.com/shop/womens-fashion-blouses-0aaz22b"

# UNCONFIRMED -- Gap Inc sites commonly use a /p/ or /product/ segment
# with a numeric SKU-like ID; adjust from real printed output on first run.
PDP_LINK_RE = re.compile(r'href="([^"]*/(?:browse/product|p)/[a-z0-9\-]*\d{5,}[^"]*)"')

CATEGORY_MAP = {
    "sweaters-and-cardigans": "sweaters",
    "sweater": "sweaters",
    "cardigan": "sweaters",
    "fashion-blouses": "blouses",
    "blouse": "blouses",
    "shirt": "blouses",
}

CURRENCY = "USD"


class OldNavyScraper(PlaywrightScraper):
    source_name = "old_navy"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)
        print(f"[old_navy] fetching category page: {url}", flush=True)
        html = self.get_rendered_html(url, wait_ms=3500, scroll=True)

        raw_links = set(PDP_LINK_RE.findall(html))
        print(f"[old_navy] discovered {len(raw_links)} candidate product links on {url}", flush=True)
        if not raw_links:
            raise ScraperError(
                f"No product links matched PDP_LINK_RE on {url}. oldnavy.gap.com's "
                "real link structure could not be confirmed from the sandboxed "
                "build environment (no internet access there). Re-run this "
                "scraper, inspect the printed candidate count, and tighten "
                "PDP_LINK_RE in app/scrapers/old_navy.py from the real output "
                "before trusting this source. Not fabricating data."
            )

        product_urls = [urljoin(url, p) for p in raw_links]
        total = len(product_urls)
        print(f"[old_navy] found {total} product URLs -- scraping each one now...", flush=True)

        products: list[ScrapedProduct] = []
        for i, purl in enumerate(product_urls, start=1):
            try:
                product = self.scrape_product(purl, category_hint=category, referer=url)
                products.append(product)
                print(f"[old_navy] ({i}/{total}) OK: {product.product_name}", flush=True)
            except ScraperError as e:
                print(f"[old_navy] ({i}/{total}) SKIP: {purl} -- {e}", flush=True)
                continue
            except Exception as e:
                print(f"[old_navy] ({i}/{total}) SKIP (unexpected): {purl} -- {e}", flush=True)
                continue

        print(f"[old_navy] done -- {len(products)}/{total} products scraped successfully.", flush=True)

        if not products:
            raise ScraperError(
                f"Found {total} product URLs on {url} but every single one failed to scrape "
                "(see per-product SKIP lines above). Not fabricating data."
            )
        return products

    def scrape_product(
        self, url: str, category_hint: Optional[str] = None, referer: Optional[str] = None
    ) -> ScrapedProduct:
        # referer=the category page: several Gap-family sites (and
        # oldnavy.mx specifically, in this project's earlier live
        # testing) have flagged referer-less direct navigation to a deep
        # product URL as bot-like -- passing it costs nothing and may
        # help here too.
        html = self.get_rendered_html(url, wait_selector="h1", wait_ms=1500, referer=referer)
        return parse_generic_product(
            html, url, self.source_name, brand="Old Navy", category_hint=category_hint, currency=CURRENCY
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
    #   cd backend && python -m app.scrapers.old_navy
    scraper = OldNavyScraper(headless=True)
    try:
        products = scraper.scrape_category(CATEGORY_URL_SWEATERS)
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()