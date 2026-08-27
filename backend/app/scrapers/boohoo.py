"""
Boohoo scraper.

UPDATED with real, user-confirmed category URLs (2026-08-26). Two
important differences from the original guess:

  1. The two working URLs use DIFFERENT domains/subdomains:
     - Blouses: https://www.boohoo.com/... (UK site, GBP)
     - Sweaters: https://us.boohoo.com/... (US site, USD)
     BASE_URL is no longer hardcoded -- it's derived from whichever
     category URL is actually passed in, and currency is inferred from
     that same domain (see _currency_for_url).
  2. PDP link pattern is still UNCONFIRMED against real HTML (this
     project's build environment has no internet access at all). This
     version casts a wide net (any .html link with a product-code-shaped
     segment) and prints exactly what it finds so a human can tighten
     PDP_LINK_RE from real output on the first live run.

PROGRESS LOGGING + RESILIENCE added to match the pattern used elsewhere
in this project: prints per-product progress, and raises a clear
ScraperError (rather than a misleading "success" with 0 products) if
every discovered link fails to scrape.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

# Real, user-confirmed category URLs (2026-08-26):
CATEGORY_URL_SWEATERS = "https://us.boohoo.com/categories/womens-knitwear-jumpers"
CATEGORY_URL_BLOUSES = "https://www.boohoo.com/categories/womens-tops-shirts-and-blouses"

# Wide net: any .html link containing a product-code-shaped segment
# (letters+digits, 5+ chars). UNCONFIRMED against real HTML -- adjust
# once a real category page's printed candidate links have been
# inspected (see the [boohoo] discovered ... print in scrape_category).
PDP_LINK_RE = re.compile(r'href="([^"]*/[A-Za-z0-9]{5,}\.html[^"]*)"')

CATEGORY_MAP = {
    "knitwear": "sweaters",
    "jumper": "sweaters",
    "sweater": "sweaters",
    "cardigan": "sweaters",
    "blouse": "blouses",
    "shirt": "blouses",
    "tops-shirts-and-blouses": "blouses",
}


def _currency_for_url(url: str) -> str:
    """boohoo.com (UK) prices in GBP; us.boohoo.com (US) prices in USD --
    inferred from the domain of whichever category URL was actually
    passed in, since this project's two confirmed working URLs use both."""
    return "USD" if urlparse(url).netloc.startswith("us.") else "GBP"


class BoohooScraper(PlaywrightScraper):
    source_name = "boohoo"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)
        currency = _currency_for_url(url)
        print(f"[boohoo] fetching category page ({currency}): {url}", flush=True)
        html = self.get_rendered_html(url, wait_ms=3000, scroll=True)

        raw_links = set(PDP_LINK_RE.findall(html))
        print(f"[boohoo] discovered {len(raw_links)} candidate product links on {url}", flush=True)
        if not raw_links:
            raise ScraperError(
                f"No product links matched PDP_LINK_RE on {url}. Boohoo's link "
                "structure could not be confirmed from the sandboxed build "
                "environment (no internet access there). Re-run this scraper, "
                "inspect the printed candidate count / save the HTML, and "
                "tighten PDP_LINK_RE in app/scrapers/boohoo.py from the real "
                "output before trusting this source. Not fabricating data."
            )

        # urljoin(url, p) resolves relative links against whichever
        # category URL was actually passed in -- correct regardless of
        # which of the two confirmed domains (us.boohoo.com or
        # www.boohoo.com) this call is for.
        product_urls = [urljoin(url, p) for p in raw_links]

        total = len(product_urls)
        print(f"[boohoo] found {total} product URLs -- scraping each one now...", flush=True)

        products: list[ScrapedProduct] = []
        for i, purl in enumerate(product_urls, start=1):
            try:
                product = self.scrape_product(purl, category_hint=category, currency=currency)
                products.append(product)
                print(f"[boohoo] ({i}/{total}) OK: {product.product_name}", flush=True)
            except ScraperError as e:
                print(f"[boohoo] ({i}/{total}) SKIP: {purl} -- {e}", flush=True)
                continue
            except Exception as e:
                print(f"[boohoo] ({i}/{total}) SKIP (unexpected): {purl} -- {e}", flush=True)
                continue

        print(f"[boohoo] done -- {len(products)}/{total} products scraped successfully.", flush=True)

        if not products:
            raise ScraperError(
                f"Found {total} product URLs on {url} but every single one failed to scrape "
                "(see per-product SKIP lines above). Not fabricating data."
            )
        return products

    def scrape_product(
        self, url: str, category_hint: Optional[str] = None, currency: str = "GBP"
    ) -> ScrapedProduct:
        html = self.get_rendered_html(url, wait_selector="h1", wait_ms=1500)
        return parse_generic_product(
            html, url, self.source_name, brand="Boohoo", category_hint=category_hint, currency=currency
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
    #   cd backend && python -m app.scrapers.boohoo
    scraper = BoohooScraper(headless=True)
    try:
        products = scraper.scrape_category(CATEGORY_URL_SWEATERS)
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()