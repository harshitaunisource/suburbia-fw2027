"""
Lili Pink (Colombia) scraper -- new competitor, pajamas category,
added 2026-09-01. UNVERIFIED against real HTML -- built on the generic
template as a starting point. Send real category-page HTML (pasted as
plain text, not an attachment) if this returns 0 products.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

CATEGORY_URL_PAJAMAS_WOMEN = "https://www.lilipink.com/mujer/pijamas"
PDP_LINK_RE = re.compile(r'href="([^"]+/p)(?:\?[^"]*)?"')
CURRENCY = "COP"


class LiliPinkScraper(PlaywrightScraper):
    source_name = "lili_pink"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        debug_path = "lili_pink_pajamas_debug.html"
        print(f"[lili_pink] fetching category page: {url}", flush=True)
        html = self.get_rendered_html(url, wait_ms=8000, scroll=True, debug_save_path=debug_path)

        links = sorted(set(PDP_LINK_RE.findall(html)))
        print(f"[lili_pink] found {len(links)} candidate links (debug HTML saved to {debug_path})", flush=True)
        if not links:
            raise ScraperError(
                f"No product links matched on {url}. Inspect {debug_path} and paste "
                f"real product-card HTML (as plain text) to fix PDP_LINK_RE. Not fabricating data."
            )

        product_urls = [urljoin(url, link) for link in links]
        total = len(product_urls)
        products: list[ScrapedProduct] = []
        for i, purl in enumerate(product_urls, start=1):
            try:
                product_html = self.get_rendered_html(purl, wait_selector="h1", wait_ms=2000)
                parsed = parse_generic_product(
                    product_html, purl, self.source_name, brand="Lili Pink",
                    category_hint="pajamas", currency=CURRENCY,
                )
                parsed.subcategory = "women"
                products.append(parsed)
                print(f"[lili_pink] ({i}/{total}) OK: {parsed.product_name}", flush=True)
            except ScraperError as e:
                print(f"[lili_pink] ({i}/{total}) SKIP: {purl} -- {e}", flush=True)
                continue
            except Exception as e:
                print(f"[lili_pink] ({i}/{total}) SKIP (unexpected): {purl} -- {e}", flush=True)
                continue

        print(f"[lili_pink] done -- {len(products)}/{total} scraped.", flush=True)
        if not products:
            raise ScraperError(f"Found {total} URLs but all failed to scrape. Not fabricating data.")
        return products

    def scrape_product(self, url: str, category_hint: Optional[str] = None) -> ScrapedProduct:
        html = self.get_rendered_html(url, wait_selector="h1", wait_ms=2000)
        return parse_generic_product(
            html, url, self.source_name, brand="Lili Pink",
            category_hint=category_hint or "pajamas", currency=CURRENCY,
        )