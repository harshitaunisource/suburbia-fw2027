"""
Textilon scraper (bo.textilon.com) -- new buyer/brand, added 2026-09-01,
focused on the pajamas category for an active buyer conversation.

REAL RISK, FLAGGED UPFRONT: "bo." is a very common subdomain convention
for "back office" (Spanish/French/Portuguese business platforms) -- an
internal admin/wholesale-ordering panel, not necessarily a public
storefront. This project has NO internet access to verify which one
bo.textilon.com actually is before you run this live. If it requires a
login, the rendered HTML will show a login form / redirect instead of a
product grid -- the debug HTML dump (see debug_save_path below) will
make this obvious on the very first run, and if so, this scraper cannot
proceed without real login credentials being supplied (a materially
different, higher-risk kind of access this project has deliberately
avoided elsewhere -- see the Zara/H&M docstrings on not defeating
anti-bot/access-control systems). This is not a guess to be resolved
blind a second time; if it's gated, tell me what you see and we'll
decide how to proceed together.

CURRENCY: assumed MXN (unverified) given the Spanish-language,
Mexico-consistent URL structure matching Suburbia's own storefront
conventions. Confirm/correct once real data comes back.

Built on the same proven generic template (OpenGraph + JSON-LD image
fallback + composition extraction + category-sanity keyword check)
already used successfully for Boohoo, SHEIN, Target, and Primark --
NOT verified against real HTML yet. Expect the same one-or-two-iteration
tightening loop already used repeatedly in this project: run it, inspect
the debug HTML dump if it finds 0 products, tighten PDP_LINK_RE from
real evidence.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

BASE_URL = "https://bo.textilon.com"

# Real, user-provided category URLs (2026-09-01). Focus is explicitly
# women's pajamas first -- men's is lower priority per instruction ("if
# scraping both is time taking or errors shown... focus on women").
CATEGORY_URL_PAJAMAS_WOMEN = "https://bo.textilon.com/articulos/categoria/mujer/subcategoria/pijamas"
CATEGORY_URL_PAJAMAS_MEN = "https://bo.textilon.com/articulos/categoria/hombre/subcategoria/pijamas"

# CONFIRMED via a real product page (2026-09-01):
# https://bo.textilon.com/producto/NVC013-201 -- real pattern is
# /producto/<code>, not the guessed /articulos/producto/... etc.
PDP_LINK_RE = re.compile(r'href="(/producto/[A-Za-z0-9\-]+)"')

# CONFIRMED via real DOM inspection (2026-09-01): the category page's
# product cards are <div class="cursor-pointer">, NOT <a href> tags at
# all -- this is a Vue.js SPA using JavaScript click handlers for
# navigation, so PDP_LINK_RE above will NEVER match anything on this
# page no matter how it's tuned; there is no href to find. Confirmed
# real product-card HTML:
#   <img alt="NVC002-101-PIJAMA CAMISON CON ENCAJE - JAGUARES"
#        src=".../pijamas_500x600/NVC002-101.jpg">
# The product CODE is embedded in the image filename, and matches the
# exact same NVCxxx-xxx shape as the confirmed working product page URL
# (bo.textilon.com/producto/NVC013-201) -- so product URLs are built
# directly from image filenames instead of depending on any link at all.
IMAGE_CODE_RE = re.compile(r'/([A-Za-z]{2,5}\d{2,5}-\d{2,5})\.(?:jpg|jpeg|png|webp)', re.IGNORECASE)

# CONFIRMED via the real product page: prices display as "Bs. 249.50"
# -- Bs. is the symbol for Bolivianos (Bolivia's currency). "bo." in the
# domain is Bolivia's country code, not "back office" as originally
# guessed -- this is a genuine public storefront, not a gated admin
# panel, confirmed by the real page rendering a normal product listing
# with an "AÑADIR AL CARRITO" (add to cart) button.
CURRENCY = "BOB"


class TextilonScraper(PlaywrightScraper):
    source_name = "textilon"

    def _fetch_category_with_retry(self, url: str, debug_path: str):
        """Fetches the category page and extracts links/codes, retrying
        ONCE with a longer wait if the first attempt found nothing --
        confirmed live this URL's product-loading is a genuine timing
        race, not a structural problem (see caller's comment)."""
        for attempt, wait_ms in enumerate([12000, 18000], start=1):
            html = self.get_rendered_html(url, wait_ms=wait_ms, scroll=True, debug_save_path=debug_path)
            links = sorted(set(PDP_LINK_RE.findall(html)))
            codes = sorted(set(IMAGE_CODE_RE.findall(html))) if not links else []
            print(f"[textilon] attempt {attempt} (wait={wait_ms}ms): "
                  f"{len(links)} href links, {len(codes)} image codes, {len(html)} chars", flush=True)
            if links or codes:
                return html, links, codes
            if attempt == 1:
                print(f"[textilon] attempt 1 found nothing -- retrying with a longer wait "
                      f"(confirmed flaky between runs live)...", flush=True)
        return html, links, codes

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category_hint = "pajamas"
        subcategory = "women" if "/mujer/" in url else ("men" if "/hombre/" in url else None)

        debug_path = f"textilon_{subcategory or 'unknown'}_debug.html"
        print(f"[textilon] fetching category page: {url}", flush=True)
        # Priority fix (2026-09-01): confirmed live that this exact URL
        # returns wildly different content between runs -- one run found
        # 12 real products, the very next run (same URL, same code)
        # found 0 candidates via EITHER approach, with a debug HTML dump
        # roughly half the size of the successful run's. This is a
        # timing race on the SPA's product-loading API call, not a
        # structural problem -- retry once with an even longer wait
        # before giving up, since Textilon is the priority buyer for
        # this comparison.
        html, links, codes = self._fetch_category_with_retry(url, debug_path)

        # Early, honest check for a login wall -- see module docstring.
        lowered = html.lower()
        if any(marker in lowered for marker in ["type=\"password\"", "iniciar sesión", "login", "log in"]):
            raise ScraperError(
                f"{url} appears to require a login (found a password field or "
                f"login-related text in the rendered page). This scraper does "
                f"NOT attempt to authenticate -- inspect {debug_path} to confirm, "
                f"and if so, real login credentials would be needed to proceed, "
                f"which is a materially different kind of access than public "
                f"scraping. Not fabricating data."
            )

        if links:
            product_urls = [urljoin(url, link) for link in links]
        else:
            product_urls = [f"{BASE_URL}/producto/{code}" for code in codes]
            if not product_urls:
                raise ScraperError(
                    f"Found neither <a href> links nor recognizable product-code image "
                    f"filenames on {url} even after a retry. Inspect {debug_path} -- the "
                    f"page's real structure differs from both approaches tried so far. "
                    f"Not fabricating data."
                )

        total = len(product_urls)
        print(f"[textilon] found {total} product URLs -- scraping each one now...", flush=True)

        products: list[ScrapedProduct] = []
        for i, purl in enumerate(product_urls, start=1):
            try:
                product_html = self.get_rendered_html(purl, wait_selector="h1", wait_ms=8000)
                parsed = parse_generic_product(
                    product_html, purl, self.source_name, brand="Textilon",
                    category_hint=category_hint, currency=CURRENCY,
                    # Textilon product names legitimately contain " - "
                    # as part of the name itself (e.g. "PIJAMA CAMISON
                    # CON ENCAJE - JAGUARES", where "JAGUARES" is the
                    # print/pattern name) -- confirmed live, the default
                    # title-cleaning logic was truncating real product
                    # names by treating " - " as a site-suffix separator
                    # to strip. Only split on "|" here, not " - ".
                    title_separators=("|",),
                )
                parsed.subcategory = subcategory
                # FIX for confirmed live bug: og:image on Textilon is
                # ALWAYS "/logos/logo_textilon_900.jpg" -- the site's
                # generic logo, not the product photo (and a relative
                # URL besides, which is why image downloads failed with
                # "Invalid URL"). The real product image URL follows a
                # confirmed, predictable pattern (verified via real
                # DevTools inspection): construct it directly from the
                # product code instead of trusting the broken meta tag.
                code_match = re.search(r"/producto/([A-Za-z0-9\-]+)", purl)
                if code_match:
                    gender_folder = "MUJER" if subcategory == "women" else "HOMBRE"
                    parsed.image_url = (
                        f"https://textilon-store.nyc3.digitaloceanspaces.com/bo/"
                        f"{gender_folder}/pijamas_500x600/{code_match.group(1)}.jpg"
                    )
                products.append(parsed)
                print(f"[textilon] ({i}/{total}) OK: {parsed.product_name}", flush=True)
            except ScraperError as e:
                print(f"[textilon] ({i}/{total}) SKIP: {purl} -- {e}", flush=True)
                continue
            except Exception as e:
                print(f"[textilon] ({i}/{total}) SKIP (unexpected): {purl} -- {e}", flush=True)
                continue

        print(f"[textilon] done -- {len(products)}/{total} products scraped successfully.", flush=True)

        if not products:
            raise ScraperError(
                f"Found {total} product URLs on {url} but every single one failed to scrape "
                f"(see per-product SKIP lines above). Not fabricating data."
            )
        return products

    def scrape_product(self, url: str, category_hint: Optional[str] = None) -> ScrapedProduct:
        html = self.get_rendered_html(url, wait_selector="h1", wait_ms=8000)
        return parse_generic_product(
            html, url, self.source_name, brand="Textilon", category_hint=category_hint or "pajamas",
            currency=CURRENCY, title_separators=("|",),
        )


if __name__ == "__main__":
    # Manual smoke test -- run from a machine with real internet access:
    #   cd backend && python -m app.scrapers.textilon
    scraper = TextilonScraper(headless=True)
    try:
        products = scraper.scrape_category(CATEGORY_URL_PAJAMAS_WOMEN)
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()