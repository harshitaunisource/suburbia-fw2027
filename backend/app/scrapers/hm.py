"""
H&M scraper.

UPDATED with real, user-confirmed category URLs (2026-08-26) -- on the
India storefront (en_in locale), in English, not the original es_mx
(Mexico) URLs this scraper was first built against. This required two
classes of fix, not just swapping the URL:

  1. PDP_LINK_RE was hardcoded to /es_mx/productpage... -- generalized to
     accept any locale segment (e.g. /en_in/productpage...).
  2. ALL the text-parsing logic (price anchor "Precio", attribute labels
     like "Ajuste"/"Cuello", the "Materiales" section) was written
     assuming Spanish page text. Rewritten below to try the English
     equivalent first, falling back to the Spanish version, so this
     scraper works against either locale rather than silently returning
     empty attributes on an English page that actually loaded fine.
  3. Currency: en_in prices in INR, not MXN -- was previously hardcoded
     to MXN (same class of bug already caught once on ASOS/Zara).

WHY PLAYWRIGHT: a plain httpx GET (even with a full, realistic browser
header set) gets rejected with a 403 from Akamai on both the category
and product pages of the Mexico store -- confirmed live via the
errors.edgesuite.net reference page. Whether the India-locale URLs are
protected the same way is UNCONFIRMED -- a prior run against the es_mx
URLs failed on literally every single product page (130/130) even via
Playwright, which is a strong signal this is Akamai blocking at the
product-page level specifically, independent of locale. Don't be
surprised if this locale also fails outright -- see this scraper's
CHANGELOG note in the project conversation for the full picture before
spending more time on H&M specifically.

IMPORTANT: still not executable from the sandboxed build environment
(no outbound network access). Smoke-test it the same way every other
scraper in this project was validated.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import PlaywrightScraper, ScraperError

BASE_URL = "https://www2.hm.com"

# Generalized to any locale segment (e.g. es_mx, en_in, en_us) -- was
# hardcoded to /es_mx/ only, which would find zero products against the
# real, user-confirmed en_in URLs below.
PDP_LINK_RE = re.compile(r"/[a-z]{2}_[a-z]{2}/productpage\.(\d+)\.html")
PRICE_RE = re.compile(r"[\$\u20b9]\s?([\d,]+\.?\d{0,2})")
ARTICLE_NUM_RE = re.compile(r"Art\.?\s*n[uú]?m?\.?:?\s*(\d+)", re.IGNORECASE)

# Real, user-confirmed category URLs (2026-08-26), India storefront:
CATEGORY_URL_SWEATERS = "https://www2.hm.com/en_in/women/shop-by-product/cardigans-jumpers/jumpers.html"
CATEGORY_URL_BLOUSES = "https://www2.hm.com/en_in/women/shop-by-product/shirts-blouses.html"

# India storefront prices in INR -- do not silently mislabel these as
# MXN (same class of bug already fixed once on ASOS/Zara).
CURRENCY = "INR"

PRICE_ANCHOR_WORDS = ["Precio", "Price"]

# Known attribute labels -> normalized field name, Spanish first
# (originally confirmed live on the Mexico store) then English
# equivalents (unconfirmed -- best-effort guess at H&M's English label
# wording). Extend this if other garment types show new labels.
LABEL_FIELDS = {
    "Longitud": "length",
    "Length": "length",
    "Largo de manga": "sleeve_length",
    "Sleeve length": "sleeve_length",
    "Ajuste": "fit",
    "Fit": "fit",
    "Cuello": "neckline",
    "Neckline": "neckline",
    "Talle": "rise",
    "Tiro": "rise",
    "Rise": "rise",
}

MATERIALS_SECTION_MARKERS = [
    ("Materiales", "Gu\u00eda de cuidados"),
    ("Composition", "Care instructions"),
    ("Materials", "Care guide"),
]

CATEGORY_MAP = {
    "sueteres": "sweaters",
    "blusas": "blouses",
    "camisas-blusas": "blouses",
    # English (India / other EN locales):
    "cardigans-jumpers": "sweaters",
    "jumpers": "sweaters",
    "knitwear": "sweaters",
    "shirts-blouses": "blouses",
}


class HMScraper(PlaywrightScraper):
    source_name = "hm"

    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)
        product_ids: set[str] = set()
        page_num = 1

        while True:
            page_url = url if page_num == 1 else f"{url}?page={page_num}"
            print(f"[hm] fetching category page {page_num}: {page_url}", flush=True)
            html = self.get_rendered_html(page_url, wait_ms=3500, scroll=True)

            found = set(PDP_LINK_RE.findall(html))
            new_ids = found - product_ids
            if not new_ids:
                break  # no new products on this "page" -> either done, or
                # ?page=N isn't the real pagination mechanism (see docstring)
            product_ids |= new_ids

            page_num += 1
            if max_pages and page_num > max_pages:
                break

        if not product_ids:
            raise ScraperError(
                f"No product links found on {url} (or its ?page=N variants). "
                "This does NOT necessarily mean H&M has no products here -- "
                "PDP_LINK_RE or the pagination mechanism assumed in this "
                "scraper's docstring may not match the real live page, or "
                "this locale is blocked the same way the Mexico store's "
                "product pages were (130/130 blocked in a prior run). "
                "Not fabricating data."
            )

        # PDP_LINK_RE now only captures the numeric id; rebuild the real
        # locale-prefixed path from the page HTML itself rather than
        # assuming a fixed locale, since scrape_category can be called
        # against different locale URLs (es_mx, en_in, ...).
        locale_match = re.search(r"/([a-z]{2}_[a-z]{2})/productpage\.\d+\.html", "".join(found) or url)
        locale = locale_match.group(1) if locale_match else "en_in"

        total = len(product_ids)
        print(f"[hm] found {total} product IDs -- scraping each one now...", flush=True)

        products: list[ScrapedProduct] = []
        for i, pid in enumerate(sorted(product_ids), start=1):
            purl = f"{BASE_URL}/{locale}/productpage.{pid}.html"
            try:
                product = self.scrape_product(purl, category_hint=category)
                products.append(product)
                print(f"[hm] ({i}/{total}) OK: {product.product_name}", flush=True)
            except ScraperError as e:
                print(f"[hm] ({i}/{total}) SKIP: {purl} -- {e}", flush=True)
                continue
            except Exception as e:
                print(f"[hm] ({i}/{total}) SKIP (unexpected): {purl} -- {e}", flush=True)
                continue
        print(f"[hm] done -- {len(products)}/{total} products scraped successfully.", flush=True)
        return products

    def scrape_product(self, url: str, category_hint: Optional[str] = None) -> ScrapedProduct:
        html = self.get_rendered_html(url, wait_selector="h1", wait_ms=1500)
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        name = self._text_or_none(soup.select_one("h1"))
        if not name:
            raise ScraperError(f"Could not find product name (h1) for {url} -- page may not have loaded.")

        og_image = soup.select_one("meta[property='og:image']")
        main_image = og_image["content"] if og_image and og_image.get("content") else None

        gallery_images = sorted(set(re.findall(
            r"https://image\.hm\.com/assets/hm/[\w/]+\.jpg(?:\?[\w=&]*)?", html
        )))
        additional_images = [g for g in gallery_images if g != main_image]

        article_match = ARTICLE_NUM_RE.search(text)
        product_code = article_match.group(1) if article_match else self._product_code_from_url(url)

        price, original_price = self._extract_prices(text)

        attrs = self._extract_labeled_attributes(text)
        material = self._extract_materials(text)

        discount_pct = None
        if price and original_price and original_price > price:
            discount_pct = round((1 - price / original_price) * 100, 1)

        category = category_hint or self._category_from_breadcrumb(soup)

        return ScrapedProduct(
            source=self.source_name,
            brand="H&M",
            category=category,
            subcategory=None,
            product_name=name.strip(),
            product_code=product_code,
            product_url=url,
            image_url=main_image,
            additional_image_urls=additional_images,
            price=price,
            currency=CURRENCY,
            original_price=original_price if original_price != price else None,
            discount_price=price if original_price and original_price != price else None,
            discount_percentage=discount_pct,
            description=None,  # not confirmed present as a distinct field yet
            material=material,
            sizes=[],  # not confirmed live -- see docstring
            colors=[],  # not confirmed live -- see docstring
            availability="in_stock",
        )

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _category_from_url(url: str) -> str:
        lower = url.lower()
        for k, v in CATEGORY_MAP.items():
            if k in lower:
                return v
        return "unknown"

    @staticmethod
    def _category_from_breadcrumb(soup: BeautifulSoup) -> str:
        crumbs = " ".join(a.get_text(" ", strip=True).lower() for a in soup.select("a[href*='hm.com']"))
        if "su\u00e9ter" in crumbs or "jumper" in crumbs or "cardigan" in crumbs or "knit" in crumbs:
            return "sweaters"
        if "blusa" in crumbs or "blouse" in crumbs or "shirt" in crumbs:
            return "blouses"
        return "unknown"

    @staticmethod
    def _product_code_from_url(url: str) -> Optional[str]:
        m = PDP_LINK_RE.search(url)
        return m.group(1) if m else None

    @staticmethod
    def _text_or_none(el) -> Optional[str]:
        return el.get_text(strip=True) if el else None

    @staticmethod
    def _extract_prices(text: str):
        """Looks for price amounts near a 'Precio'/'Price' anchor word,
        trying each language in turn. Confirmed live pattern on the
        Mexico store: 'Precio: $549.00$549.00' when there's no discount
        (same value twice) -- the English equivalent is unconfirmed."""
        for anchor in PRICE_ANCHOR_WORDS:
            idx = text.find(anchor)
            if idx != -1:
                break
        else:
            idx = -1
        window = text[idx: idx + 200] if idx != -1 else text[:200]
        prices = [float(p.replace(",", "")) for p in PRICE_RE.findall(window)]
        if not prices:
            return None, None
        current = prices[0]
        original = next((p for p in prices[1:] if p != current), None)
        return current, original

    @staticmethod
    def _extract_labeled_attributes(text: str) -> dict:
        """Pulls 'Label\\nValue' pairs for the known H&M attribute labels
        (see LABEL_FIELDS) out of the flattened page text -- tries every
        known label (Spanish and English) rather than assuming one
        locale."""
        result = {}
        for label, field in LABEL_FIELDS.items():
            if field in result:
                continue  # already found via another language's label
            m = re.search(rf"{re.escape(label)}:?\s*\n([^\n]+)", text)
            if m:
                result[field] = m.group(1).strip()
        return result

    @staticmethod
    def _extract_materials(text: str) -> Optional[str]:
        """Extracts material names from the composition/materials
        section, trying Spanish then English section markers."""
        for start_marker, end_marker in MATERIALS_SECTION_MARKERS:
            start = text.find(start_marker)
            if start != -1:
                end = text.find(end_marker)
                section = text[start: end if end != -1 else start + 1000]
                # Material names are short standalone lines immediately
                # followed by a capitalized explanatory sentence.
                names = re.findall(
                    r"\n([a-zA-Z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)\n[A-Z]", section
                )
                if names:
                    return ", ".join(dict.fromkeys(names))
        return None


if __name__ == "__main__":
    # Manual smoke test -- run this from a machine with real internet access
    # AND `playwright install chromium` already done:
    #   cd backend && python -m app.scrapers.hm
    scraper = HMScraper(headless=True)
    try:
        products = scraper.scrape_category(CATEGORY_URL_SWEATERS, max_pages=1)
        print(f"Scraped {len(products)} products from page 1")
        for p in products[:3]:
            print(p)
    finally:
        scraper.close()