"""
C&A Mexico scraper.

STATUS: built from real inspected content (category + product page fetched
directly 2026-08-25), NOT yet execution-tested from a real Python/httpx
client (same sandbox network limitation as every other scraper here --
my fetch tool succeeded, but that doesn't guarantee a plain script client
will; smoke-test before trusting, per the pattern established throughout
this project).

GOOD SIGN: cyamoda.com runs on Salesforce Commerce Cloud (confirmed via
demandware.static asset URLs), which is generally SEO/SSR-friendly --
similar tier to Old Navy's VTEX, likely easier than Zara/H&M's Akamai.

STRUCTURE:
  Category: https://www.cyamoda.com/mujer/ropa/sueteres/
    Real product cards inline: name as "### [Name](url)", price as either
    plain "$XXX.XX" or "~~Precio reducido de $XXX.XX a~~ $YYY.YY" when
    discounted. Each product card also lists color-swatch links -- each
    swatch points to a DIFFERENT product URL/code for that color variant
    (i.e. one "product" in the catalogue sense = one specific color, not
    a parent with sub-colors). "Cargar más productos..." spinner suggests
    infinite-scroll for categories bigger than what's server-rendered
    initially; the 16-product category tested rendered fully in one
    request with no scrolling, so pagination behavior for larger
    categories is UNCONFIRMED.

  Product: https://www.cyamoda.com/<slug>/<code>.html
    Excellent structured data, confirmed live:
      - <meta property="og:product:price:amount" content="299.00 MXN">
        -- direct machine-readable price! No fragile regex needed for the
        current price (see _extract_price_from_meta).
      - <meta property="og:image">, <meta property="og:title">,
        <meta property="og:description">
      - "Precio reducido de $X.XX a $Y.YY" text pattern gives BOTH list
        and sale price when discounted (meta tag only gives the sale/
        current price)
      - "Mod:<code>" text = product code (matches URL)
      - A clean attribute table: Color / Estilo (fit) / Estampado
        (pattern) / Largo (length)
      - "Composición" section = material composition string, e.g.
        "POLIAMIDA/NYLON 20%,VISCOSA/RAYÓN 80%"
      - Explicit size list (ECH/CH/M/G/EG) and color swatch names
      - "¡Últimas existencias!" = low-stock text warning

NOT YET CONFIRMED:
  - Category pagination beyond what renders in the first request
  - Gallery images beyond the single og:image (product page showed
    multiple color-swatch thumbnail images but not a full gallery for
    the SELECTED color)
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedProduct, ScraperError

BASE_URL = "https://www.cyamoda.com"

PDP_LINK_RE = re.compile(r"/[a-z0-9\-]+/\d{5,8}\.html")
PRICE_RE = re.compile(r"\$([\d,]+\.\d{2})")
MOD_RE = re.compile(r"Mod:(\d+)")
COMPOSITION_RE = re.compile(r"Composici[oó]n\s*\n?\s*([^\n]+)", re.IGNORECASE)
SIZE_TOKENS = ["ECH", "CH", "M", "G", "EG", "1EG", "2EG"]

CATEGORY_MAP = {
    "sueteres": "sweaters",
    "blusas": "blouses",
}


class CAndAScraper(BaseScraper):
    source_name = "c_and_a"

    # ---------------------------------------------------------------- category
    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        category = self._category_from_url(url)

        resp = self.client.get(url)
        if resp.status_code == 403:
            raise ScraperError(f"C&A blocked the request (403): {url}")
        resp.raise_for_status()

        # The page template includes a "Te podría gustar" recommendation
        # widget with unrelated products (confirmed live: shirts, jeans,
        # dresses) BEFORE the real product grid on every page. Bounding
        # extraction to between "Ver resultados (" and "Ver todo" avoids
        # scraping that widget as if it were part of this category.
        html = resp.text
        start = html.find("Ver resultados (")
        end = html.find("Ver todo", start) if start != -1 else -1
        window = html[start:end] if start != -1 and end != -1 else html

        product_paths = sorted(set(PDP_LINK_RE.findall(window)))
        product_urls = [urljoin(BASE_URL, p) for p in product_paths]

        # NOTE: category page showed a "Cargando más productos..." spinner,
        # suggesting infinite-scroll for categories with more products than
        # fit in the initial server-rendered batch. The 16-product category
        # tested returned all 16 in one request. For larger categories this
        # may silently under-count -- compare against the "(N)" result
        # count shown on the page before trusting a large category's totals.

        products: list[ScrapedProduct] = []
        for purl in product_urls:
            try:
                products.append(self.scrape_product(purl, category_hint=category))
            except ScraperError:
                continue
        return products

    # ----------------------------------------------------------------- product
    def scrape_product(self, url: str, category_hint: Optional[str] = None) -> ScrapedProduct:
        resp = self.client.get(url)
        if resp.status_code == 403:
            raise ScraperError(f"C&A blocked the request (403): {url}")
        resp.raise_for_status()

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        name = self._text_or_none(soup.select_one("h1")) or self._meta_content(soup, "og:title")
        if not name:
            raise ScraperError(f"Could not find product name for {url}")
        name = re.sub(r"\s*\|\s*C&A M[eé]xico.*$", "", name).strip()

        main_image = self._meta_content(soup, "og:image")

        code_match = re.search(r"/(\d{5,8})\.html$", url)
        product_code = code_match.group(1) if code_match else None

        price = self._extract_price_from_meta(soup)
        original_price = self._extract_original_price(text)
        if original_price == price:
            original_price = None

        description = self._meta_content(soup, "og:description")
        material = self._extract_material(text)
        sizes = self._extract_sizes(text)
        colors = self._extract_colors(soup, text)

        availability = "low_stock" if "\u00daltimas existencias" in text else "in_stock"

        discount_pct = None
        if price and original_price and original_price > price:
            discount_pct = round((1 - price / original_price) * 100, 1)

        category = category_hint or self._category_from_breadcrumb(soup)

        return ScrapedProduct(
            source=self.source_name,
            brand="C&A",
            category=category,
            subcategory=None,
            product_name=name,
            product_code=product_code,
            product_url=url,
            image_url=main_image,
            additional_image_urls=[],  # full gallery for selected color not yet confirmed
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
        crumbs = " ".join(a.get_text(" ", strip=True).lower() for a in soup.select("a[href]"))
        if "su\u00e9ter" in crumbs:
            return "sweaters"
        if "blusa" in crumbs:
            return "blouses"
        return "unknown"

    @staticmethod
    def _meta_content(soup: BeautifulSoup, prop: str) -> Optional[str]:
        el = soup.select_one(f"meta[property='{prop}']") or soup.select_one(f"meta[name='{prop}']")
        return el["content"].strip() if el and el.get("content") else None

    @staticmethod
    def _text_or_none(el) -> Optional[str]:
        return el.get_text(strip=True) if el else None

    @classmethod
    def _extract_price_from_meta(cls, soup: BeautifulSoup) -> Optional[float]:
        raw = cls._meta_content(soup, "og:product:price:amount")
        if not raw:
            return None
        m = re.search(r"([\d.]+)", raw)
        return float(m.group(1)) if m else None

    @staticmethod
    def _extract_original_price(text: str) -> Optional[float]:
        """From 'Precio reducido de $X.XX a $Y.YY' -- returns the list
        price (X), or None if that phrase isn't present (not discounted)."""
        m = re.search(r"Precio reducido de\s*\$([\d,]+\.\d{2})\s*a", text)
        return float(m.group(1).replace(",", "")) if m else None

    @staticmethod
    def _extract_material(text: str) -> Optional[str]:
        m = COMPOSITION_RE.search(text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_sizes(text: str) -> list[str]:
        """Looks for the standard C&A size-token list appearing as
        standalone lines (confirmed pattern: 'Tallas\\nECH\\nCH\\nM\\nG\\nEG')."""
        idx = text.find("Tallas")
        if idx == -1:
            return []
        window = text[idx: idx + 200]
        found = []
        for token in SIZE_TOKENS:
            if re.search(rf"(?:^|\n){token}(?:\n|$)", window):
                found.append(token)
        return found

    @staticmethod
    def _extract_colors(soup: BeautifulSoup, text: str) -> list[str]:
        """Color swatch alt text comes in two confirmed formats:
        product-page thumbnails: 'Suéter Abierto Bolsillos,BLANCO HUESO'
          (2 comma-separated parts -- color is the last part)
        category-card swatches: ', CREMA, swatch'
          (3 parts -- color is the SECOND-TO-LAST part, since the last
          part is literally the word 'swatch').

        IMPORTANT: the "Te podría gustar" recommendation widget also
        appears on product pages with many unrelated swatches, so we
        can't scan the whole page's <img> tags -- confirmed live (one
        product returned 18 colors including "AZUL CIELO", "CHOCOLATE"
        etc. that belonged to entirely different products). Instead,
        only consider swatch images whose alt text repeats the product's
        own name (the confirmed pattern for the SELECTED product's own
        color options), falling back to a Color/Tallas text window if
        the product name isn't in any alt text for some reason."""
        colors = []

        name_el = soup.select_one("h1")
        product_name = name_el.get_text(strip=True) if name_el else None

        candidates = soup.select("img[alt*=',']")
        if product_name:
            candidates = [img for img in candidates if img.get("alt", "").startswith(product_name)]

        for img in candidates:
            alt = img.get("alt", "")
            parts = [p.strip() for p in alt.split(",")]
            if not parts:
                continue
            if parts[-1].lower() == "swatch" and len(parts) >= 2:
                color = parts[-2]
            else:
                color = parts[-1]
            if color and color not in colors:
                colors.append(color)

        if colors:
            return colors

        # Fallback: text window between "Color" and "Tallas" headers.
        start = text.find("Color")
        end = text.find("Tallas", start)
        if start == -1:
            return []
        window = text[start:end] if end != -1 else text[start: start + 300]
        # Strip the leading "Color" label itself, then split remaining
        # lines as candidate color names (short, all-caps-ish tokens).
        for line in window.split("\n")[1:]:
            line = line.strip()
            if line and line.isupper() and line not in colors:
                colors.append(line)
        return colors


if __name__ == "__main__":
    # Manual smoke test -- run this from a machine with real internet access:
    #   cd backend && python -m app.scrapers.c_and_a
    scraper = CAndAScraper()
    try:
        products = scraper.scrape_category("https://www.cyamoda.com/mujer/ropa/sueteres/")
        print(f"Scraped {len(products)} products")
        for p in products[:5]:
            print(p)
    finally:
        scraper.close()