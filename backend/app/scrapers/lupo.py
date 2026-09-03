"""
Lupo (Brazil) scraper -- new competitor for the pajamas category,
added 2026-09-01. UNVERIFIED against real HTML (no internet access in
this build environment). Built on the same proven generic template
(OpenGraph + JSON-LD image fallback + composition extraction +
category-sanity keyword check) already used successfully for Boohoo,
SHEIN, Target, and Primark.

CURRENCY: assumed BRL (Brazilian Real) given the .com.br domain --
should be correct, but not yet confirmed against a real product page.

If this returns 0 products on the first run, inspect the debug HTML
dump it saves and tighten PDP_LINK_RE from real evidence -- same loop
already used repeatedly and successfully in this project.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

CATEGORY_URL_PAJAMAS_WOMEN = "https://www.lupo.com.br/feminino/pijamas"

# CONFIRMED PLATFORM: real DOM inspection (2026-09-01) shows VTEX
# component classes ("vtex-flex-layout", "vtex-stack-layout") -- Lupo
# runs on VTEX, Brazil's dominant e-commerce platform. VTEX has a
# well-documented, standard convention: every product-detail-page URL
# ends in "/p" (e.g. "/pijama-longo-feminino/p"). This is not a blind
# guess -- it's VTEX's own documented URL structure, used consistently
# across virtually every VTEX storefront.
PDP_LINK_RE = re.compile(r'href="([^"]+/p)(?:\?[^"]*)?"')

CURRENCY = "BRL"  # unverified, see module docstring


class LupoScraper(PlaywrightScraper):
    source_name = "lupo"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        debug_path = "lupo_pajamas_debug.html"
        print(f"[lupo] fetching category page: {url}", flush=True)
        html = self.get_rendered_html(
            url, wait_ms=5000, scroll=True, debug_save_path=debug_path, wait_until="networkidle"
        )

        links = sorted(set(PDP_LINK_RE.findall(html)))
        print(f"[lupo] found {len(links)} candidate links (debug HTML saved to {debug_path})", flush=True)

        if not links:
            raise ScraperError(
                f"No product links matched PDP_LINK_RE on {url}. Lupo's real link "
                f"structure could not be confirmed from the sandboxed build "
                f"environment. Inspect {debug_path}, find a real product link, and "
                f"tighten PDP_LINK_RE in app/scrapers/lupo.py from the real output. "
                f"Not fabricating data."
            )

        product_urls = [urljoin(url, link) for link in links]
        total = len(product_urls)
        print(f"[lupo] found {total} product URLs -- scraping each one now...", flush=True)

        products: list[ScrapedProduct] = []
        for i, purl in enumerate(product_urls, start=1):
            try:
                product_html = self.get_rendered_html(
                    purl, wait_selector="h1", wait_ms=1500, wait_until="networkidle"
                )
                parsed = parse_generic_product(
                    product_html, purl, self.source_name, brand="Lupo",
                    category_hint="pajamas", currency=CURRENCY,
                )
                parsed.subcategory = "women"
                products.append(parsed)
                print(f"[lupo] ({i}/{total}) OK: {parsed.product_name}", flush=True)
            except ScraperError as e:
                print(f"[lupo] ({i}/{total}) SKIP: {purl} -- {e}", flush=True)
                continue
            except Exception as e:
                print(f"[lupo] ({i}/{total}) SKIP (unexpected): {purl} -- {e}", flush=True)
                continue

        print(f"[lupo] done -- {len(products)}/{total} products scraped successfully.", flush=True)
        if not products:
            raise ScraperError(
                f"Found {total} product URLs on {url} but every single one failed to scrape. "
                f"Not fabricating data."
            )
        return products

    def scrape_product(self, url: str, category_hint: Optional[str] = None) -> ScrapedProduct:
        html = self.get_rendered_html(url, wait_selector="h1", wait_ms=1500, wait_until="networkidle")
        return parse_generic_product(
            html, url, self.source_name, brand="Lupo", category_hint=category_hint or "pajamas",
            currency=CURRENCY,
        )


if __name__ == "__main__":
    scraper = LupoScraper(headless=True)
    try:
        products = scraper.scrape_category(CATEGORY_URL_PAJAMAS_WOMEN)
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()