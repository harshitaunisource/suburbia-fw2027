"""
Suburbia Mexico scraper.

Site structure observed directly against real pages (2026-08-24), including
raw (un-rendered) HTML source for a product page:
  https://www.suburbia.com.mx/tienda/su%C3%A9teres/cat_SB_3008   (sweaters, 456 items / 9 pages)
  https://www.suburbia.com.mx/tienda/blusas/cat_SB_3001          (blouses)
  https://www.suburbia.com.mx/tienda/pdp/ensamble-contempo-cuello-v-para-mujer/SB5002701474

KEY FINDING (confirmed against real raw HTML, not just rendered text):
Suburbia's PDP is a Next.js app that server-renders a huge inline JSON
payload (React Server Components "flight" data, delivered via
`self.__next_f.push([1, "..."])` script tags). Inside that payload sits a
single, complete, well-typed `"product": {...}` object with everything we
need directly as real fields -- not text to regex out of a page:
  - id, title, brand, productDescription
  - minimumPromoPrice / maximumListPrice (exact numeric prices -- no need
    to scrape "$X.XX" text at all, which is what broke the first version:
    the page also contains dozens of unrelated "$X.XX" installment-payment
    strings like "$$6.00 A LA QUINCENA" deep in the same payload, and a
    naive whole-page price regex was matching those instead)
  - colorSet (colorName per color) and sizeSet (size per size)
  - variants[] -- one per color/size SKU, each with its own galleryImages,
    listPrice, promoPrice, discountPercentage
  - dynamicAttributes[] -- Suburbia has ALREADY labeled fit, neckline
    ("Cuello"), pattern ("Estampado"), material, season, occasion, etc. for
    every product. This is essentially free, pre-labeled AI-attribute data
    -- Phase 5 (AI attribute extraction) may barely need an LLM call for
    Suburbia's own catalogue; this is worth revisiting when building that
    phase. For now we only pull `material` out of it into ScrapedProduct,
    but the full list is trivially available via `_extract_dynamic_attrs`.

This makes the scraper far more robust than the original text/regex-based
version. The old text-scanning price/image logic is kept as a fallback for
robustness (e.g. if Suburbia changes their frontend framework), but should
essentially never fire in practice -- if you see a ScrapedProduct come back
with suspiciously round/small prices, check whether the JSON extraction
silently failed and it fell through to the fallback path.

IMPORTANT: Category-listing structure (pagination, PDP link discovery) was
verified with a *real* execution run against the live site and produced 56
correctly-structured products on page 1 of sweaters. Product-level JSON
extraction above was verified against one real PDP's raw HTML pasted back
into this conversation, and unit-tested with a synthetic payload matching
the exact escaping pattern Next.js uses. It has NOT yet been re-run live
end-to-end after this rewrite -- do that before trusting it further, the
same way the first two rounds of live testing caught real bugs.
"""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedProduct, ScraperError

BASE_URL = "https://www.suburbia.com.mx"

PDP_LINK_RE = re.compile(r"/tienda/pdp/[^\"'?\s]+/[A-Za-z0-9]+")

# --- fallback-only patterns (see module docstring) --------------------------
PRICE_RE = re.compile(r"\$([\d,]+\.\d{2})")
PRODUCT_CODE_MARKER_RE = re.compile(r"C[oó]digo de producto:?\s*[A-Za-z0-9]+", re.IGNORECASE)

CATEGORY_MAP = {
    "su\u00e9teres": "sweaters",
    "blusas": "blouses",
}


class SuburbiaScraper(BaseScraper):
    source_name = "suburbia"

    # ---------------------------------------------------------------- category
    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)
        product_urls: list[str] = []
        page = 1

        while True:
            page_url = url if page == 1 else f"{url.rstrip('/')}/page-{page}"
            resp = self.client.get(page_url)
            if resp.status_code == 403 or "captcha" in resp.text.lower():
                raise ScraperError(
                    f"Suburbia blocked the request (status={resp.status_code}) on {page_url}. "
                    "Site may require Playwright + a residential/session-warmed browser context "
                    "instead of a plain httpx GET. Do not fabricate data -- report and stop."
                )
            resp.raise_for_status()

            found = sorted(set(PDP_LINK_RE.findall(resp.text)))
            if not found:
                break  # no more products -> past last page

            for path in found:
                product_urls.append(urljoin(BASE_URL, path))

            total_pages = self._total_pages(resp.text)
            page += 1
            if (max_pages and page > max_pages) or (total_pages and page > total_pages):
                break

        product_urls = sorted(set(product_urls))

        products: list[ScrapedProduct] = []
        for purl in product_urls:
            try:
                products.append(self.scrape_product(purl, category_hint=category))
            except ScraperError:
                # One bad product page shouldn't kill the whole run; the
                # caller (scrape service) is responsible for logging /
                # counting this against scrape_runs.images_failed etc.
                continue
        return products

    # ----------------------------------------------------------------- product
    def scrape_product(self, url: str, category_hint: Optional[str] = None) -> ScrapedProduct:
        resp = self.client.get(url)
        if resp.status_code == 403:
            raise ScraperError(f"Suburbia blocked product page request: {url}")
        resp.raise_for_status()

        html = resp.text
        product = self._extract_embedded_product_json(html)

        if product:
            return self._from_embedded_json(product, url, category_hint)

        # Fallback path -- see module docstring. Should rarely fire.
        return self._from_text_scan(html, url, category_hint)

    # ---------------------------------------------- primary: embedded JSON path
    def _from_embedded_json(self, product: dict, url: str, category_hint: Optional[str]) -> ScrapedProduct:
        name = product.get("title")
        if not name:
            raise ScraperError(f"Embedded product JSON had no title for {url}")

        # product_code = product.get("id") or self._product_code_from_url(url)
        # brand = product.get("brand")
        # description = product.get("productDescription")
        product_code = product.get("id") or self._product_code_from_url(url)
        brand = product.get("brand")
        description = product.get("productDescription")
        if description and re.match(r"^\$\d+$", description):
            # Next.js deduplicates repeated string values across products on
            # the same page into back-references like "$429" (pointing to
            # another chunk in the RSC stream) instead of repeating the full
            # text. Resolving arbitrary cross-chunk references generically
            # is out of scope for now -- better to store no description than
            # a meaningless pointer string. Price/name/images/sizes/colors/
            # material are unaffected by this and remain reliable.
            description = None

        price = product.get("minimumPromoPrice")
        original_price = product.get("maximumListPrice")
        if price is not None and original_price is not None and price >= original_price:
            original_price = None  # not actually discounted

        discount_pct = None
        variants = product.get("variants") or []
        if variants and isinstance(variants[0].get("discountPercentage"), (int, float)):
            discount_pct = variants[0]["discountPercentage"]
        elif price and original_price and original_price > 0:
            discount_pct = round((1 - price / original_price) * 100, 1)

        main_image = product.get("largeImage") or product.get("thumbnailImage")
        gallery: list[str] = []
        if variants and variants[0].get("galleryImages"):
            gallery = list(variants[0]["galleryImages"])
        additional_images = [g for g in gallery if g != main_image]

        sizes = [s.get("size") for s in (product.get("sizeSet") or []) if s.get("size")]
        colors = [c.get("colorName") for c in (product.get("colorSet") or []) if c.get("colorName")]

        material = self._extract_dynamic_attr(product, "Material")

        availability = "in_stock"
        flags = (variants[0].get("flags") if variants else None) or {}
        limited = flags.get("limitedStock") or {}
        if limited.get("isOutOfStock"):
            availability = "out_of_stock"

        category = category_hint or self._category_from_json(product)

        return ScrapedProduct(
            source=self.source_name,
            brand=brand,
            category=category,
            subcategory=None,
            product_name=name.strip(),
            product_code=product_code,
            product_url=url,
            image_url=main_image,
            additional_image_urls=additional_images,
            price=price,
            currency="MXN",
            original_price=original_price,
            discount_price=price if original_price else None,
            discount_percentage=discount_pct,
            description=description,
            material=material,
            sizes=sizes,
            colors=colors,
            availability=availability,
        )

    # ------------------------------------------------- fallback: text scanning
    def _from_text_scan(self, html: str, url: str, category_hint: Optional[str]) -> ScrapedProduct:
        soup = BeautifulSoup(html, "html.parser")
        product_code = self._product_code_from_url(url)

        name = self._text_or_none(soup.select_one("h1"))
        if not name:
            raise ScraperError(
                f"Could not find embedded product JSON or a fallback <h1> for {url} -- "
                "page structure may have changed."
            )

        brand_el = soup.select_one("a[href*='?s=']")
        brand = self._text_or_none(brand_el)

        price, original_price = self._extract_prices_fallback(html)
        images = self._extract_gallery_images_fallback(soup, html)
        main_image = images[0] if images else None

        category = category_hint or self._category_from_breadcrumb(soup)

        discount_pct = None
        if price and original_price and original_price > 0 and price < original_price:
            discount_pct = round((1 - price / original_price) * 100, 1)

        return ScrapedProduct(
            source=self.source_name,
            brand=brand,
            category=category,
            subcategory=None,
            product_name=name.strip(),
            product_code=product_code,
            product_url=url,
            image_url=main_image,
            additional_image_urls=images[1:],
            price=price,
            currency="MXN",
            original_price=original_price,
            discount_price=price if original_price and price != original_price else None,
            discount_percentage=discount_pct,
            description=None,
            material=None,
            sizes=[],
            colors=[],
            availability="in_stock",
        )

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _category_from_url(url: str) -> str:
        decoded = unquote(url).lower()
        for k, v in CATEGORY_MAP.items():
            if k in decoded:
                return v
        return "unknown"

    @staticmethod
    def _category_from_json(product: dict) -> str:
        for cat in product.get("categories") or []:
            leaf = (cat.get("leaf") or "").lower()
            if "su\u00e9ter" in leaf:
                return "sweaters"
            if "blusa" in leaf:
                return "blouses"
        return "unknown"

    @staticmethod
    def _category_from_breadcrumb(soup: BeautifulSoup) -> str:
        crumbs = " ".join(a.get_text(" ", strip=True).lower() for a in soup.select("a[href*='/tienda/']"))
        if "su\u00e9ter" in crumbs or "sweater" in crumbs:
            return "sweaters"
        if "blusa" in crumbs:
            return "blouses"
        return "unknown"

    @staticmethod
    def _product_code_from_url(url: str) -> Optional[str]:
        m = re.search(r"/tienda/pdp/[^/]+/([A-Za-z0-9]+)", url)
        return m.group(1) if m else None

    @staticmethod
    def _total_pages(html: str) -> Optional[int]:
        pages = re.findall(r"/page-(\d+)", html)
        return max((int(p) for p in pages), default=None)

    @staticmethod
    def _text_or_none(el) -> Optional[str]:
        return el.get_text(strip=True) if el else None

    @staticmethod
    def _extract_dynamic_attr(product: dict, attribute_name: str) -> Optional[str]:
        for attr in product.get("dynamicAttributes") or []:
            if attr.get("attribute") == attribute_name:
                return attr.get("value")
        return None

    @staticmethod
    def _extract_embedded_product_json(html: str) -> Optional[dict]:
        """Pulls the `"product": {...}` object out of Suburbia's inline
        Next.js RSC payload. See module docstring for why this works and
        how it was verified. Balances braces on the *raw* (still
        JS-string-escaped) text -- this is safe because Next.js only
        escapes quotes/backslashes in that payload, never braces, so
        counting `{`/`}` directly gives the true end of the object without
        needing to fully parse the JS string literal first."""
        marker = '\\"product\\":{'
        start = html.find(marker)
        if start == -1:
            return None

        brace_start = start + len(marker) - 1
        depth = 0
        i = brace_start
        n = len(html)
        while i < n:
            c = html[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            return None  # never balanced -- truncated response, bail out

        raw = html[brace_start : i + 1]
        json_text = raw.replace('\\"', '"')
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            return None

    # -- fallback-only helpers (see _from_text_scan) --------------------------
    @staticmethod
    def _extract_prices_fallback(html: str):
        marker = PRODUCT_CODE_MARKER_RE.search(html)
        window = html[marker.end(): marker.end() + 400] if marker else html

        def is_installment_figure(text: str, end: int) -> bool:
            tail = text[end: end + 20].lower()
            return re.match(r"\s*quincenal", tail) is not None

        candidates = []
        for m in PRICE_RE.finditer(window):
            if is_installment_figure(window, m.end()):
                continue
            candidates.append(float(m.group(1).replace(",", "")))

        if not candidates:
            return None, None
        if len(candidates) >= 2:
            return candidates[0], candidates[1]
        return candidates[0], None

    @staticmethod
    def _extract_gallery_images_fallback(soup: BeautifulSoup, html: str) -> list[str]:
        og = soup.select_one("meta[property='og:image']")
        images: list[str] = []
        if og and og.get("content"):
            images.append(og["content"])
        for m in re.finditer(r"https://s[a-z]\d+\.suburbia\.com\.mx/\w+/[\w\-]+\.jpg", html):
            u = m.group(0)
            if u not in images:
                images.append(u)
        return images


if __name__ == "__main__":
    # Manual smoke test -- run this from a machine with real internet access:
    #   cd backend && python -m app.scrapers.suburbia
    scraper = SuburbiaScraper()
    try:
        products = scraper.scrape_category(
            "https://www.suburbia.com.mx/tienda/su%C3%A9teres/cat_SB_3008",
            max_pages=1,
        )
        print(f"Scraped {len(products)} products from page 1")
        for p in products[:3]:
            print(p)
    finally:
        scraper.close()