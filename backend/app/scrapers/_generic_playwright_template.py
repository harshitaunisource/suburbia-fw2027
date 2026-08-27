"""
Generic, reusable parsing helpers shared by the Playwright-based scrapers
(Zara, Primark, Target, SHEIN, Boohoo, ASOS) whose product pages mostly
expose standard OpenGraph / e-commerce meta tags. Centralizing this avoids
re-implementing (and re-breaking, as happened live with ASOS) the same
og:title / og:image / price-window logic six separate times.

IMPORTANT / HONESTY NOTE (read before trusting any scraper built on this):
This project's build environment has NO outbound internet access at all,
so none of the CSS selectors, URL patterns, or "known good" text anchors
below could be verified against the real, live HTML of these sites the
way Suburbia, Old Navy, C&A and H&M's scrapers were (those were built and
iterated against real fetched pages in earlier sessions -- see their
docstrings and git history). Every scraper built on this template is a
best-effort, standards-based implementation that:
  - Never fabricates data. If required fields (at minimum: name + URL)
    can't be found, it raises ScraperError and reports the failure
    instead of guessing.
  - Uses the same defensive parsing patterns (anchored price windows,
    safe None handling, per-product try/except) already validated live
    elsewhere in this project.
  - MUST be smoke-tested against the real site by you before you trust
    its output -- exactly like every other scraper here was. Expect to
    paste back real failures and iterate, the same way Suburbia/ASOS/
    Zara/SHEIN were fixed in earlier rounds.
"""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from app.scrapers._price_utils import current_and_original, discount_percentage, extract_prices_near
from app.scrapers.base import ScrapedProduct
from app.scrapers.playwright_base import ScraperError


def meta_content(soup: BeautifulSoup, prop: str) -> Optional[str]:
    el = soup.select_one(f"meta[property='{prop}']") or soup.select_one(f"meta[name='{prop}']")
    return el["content"].strip() if el and el.get("content") else None

# Substrings that indicate og:image resolved to a generic placeholder
# instead of a real product photo -- confirmed live on Primark, where
# every single product's og:image was literally
# "https://www.primark.com/assets/images/no-image.png" (which itself
# 403'd on download, but the deeper bug was extracting the wrong URL
# entirely, not a permissions problem).
PLACEHOLDER_IMAGE_MARKERS = ["no-image", "placeholder", "default-image", "noimage"]


def extract_jsonld_image(soup: BeautifulSoup) -> Optional[str]:
    """Falls back to a page's embedded schema.org Product JSON-LD data
    for the real image, when og:image is missing or a known placeholder.
    Most modern e-commerce sites populate this block with real data even
    when og:meta tags are stale/generic (as confirmed on Primark)."""
    import json as _json

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            img = item.get("image")
            if isinstance(img, list) and img:
                return img[0]
            if isinstance(img, str) and img:
                return img
    return None


def clean_title(title: Optional[str], separators: tuple[str, ...] = ("|", " - ")) -> Optional[str]:
    """Strips common site-name suffixes off an <title>/og:title value,
    e.g. 'Product Name | Brand' -> 'Product Name'."""
    if not title:
        return None
    for sep in separators:
        if sep in title:
            return title.split(sep)[0].strip()
    return title.strip()


# Bilingual (product listings in this project are ES-MX or EN-US) keyword
# sanity check: catches exactly the failure mode confirmed live on Target
# (a patio furniture "you may also like" widget link on the category page
# got scraped and saved as if it were a blouse). A category page's link
# discovery regex often can't distinguish "real product grid item" from
# "unrelated sitewide recommendation link" without knowing the site's
# exact DOM structure -- which none of these generic-template scrapers
# do yet. This is a cheap, generic backstop: if a scraped product's own
# name/description doesn't contain ANY word plausibly related to its
# claimed category, something went wrong upstream and the product is
# rejected rather than silently mislabeled.
CATEGORY_SANITY_KEYWORDS = {
    "sweaters": [
        "sweater", "cardigan", "jumper", "knit", "pullover", "sweatshirt",
        "suéter", "sueter", "cárdigan", "cardigán", "tejido", "punto",
    ],
    "blouses": [
        "blouse", "shirt", "top", "tunic", "tank", "camisole",
        "blusa", "camisa", "playera", "top", "tunica", "túnica",
    ],
}


def matches_category(name: str, description: Optional[str], category: Optional[str]) -> bool:
    """Returns True when the category is unknown/unrecognized (nothing
    to check against) or when the product's own text plausibly relates
    to it. Returns False only when we have a specific keyword list for
    this category and NONE of those words appear anywhere in the
    product's name or description -- a strong signal this link came
    from outside the actual category grid."""
    keywords = CATEGORY_SANITY_KEYWORDS.get(category or "")
    if not keywords:
        return True
    text = f"{name} {description or ''}".lower()
    return any(kw in text for kw in keywords)


def parse_generic_product(
    html: str,
    url: str,
    source_name: str,
    brand: Optional[str],
    category_hint: Optional[str],
    currency: str = "MXN",
    title_separators: tuple[str, ...] = ("|", " - "),
) -> ScrapedProduct:
    """Best-effort product-page parse using only standards-based signals
    (OpenGraph meta tags + a generically-anchored price scan). Works
    reasonably well on most modern e-commerce sites without any
    site-specific selectors, at the cost of missing fields (sizes,
    colors, material) that need site-specific structure to extract --
    those come back empty rather than guessed."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    name = meta_content(soup, "og:title")
    if not name:
        h1 = soup.select_one("h1")
        name = h1.get_text(strip=True) if h1 else None
    name = clean_title(name, title_separators)

    if not name:
        raise ScraperError(
            f"Could not find a product name (og:title or <h1>) for {url} -- "
            "page may not have rendered, or structure differs from expected."
        )

    main_image = meta_content(soup, "og:image")
    if not main_image or any(marker in main_image.lower() for marker in PLACEHOLDER_IMAGE_MARKERS):
        # og:image missing or a known placeholder (confirmed live on
        # Primark) -- try the page's structured Product data instead,
        # which usually has the real photo even when og:meta doesn't.
        jsonld_image = extract_jsonld_image(soup)
        if jsonld_image:
            main_image = jsonld_image
    description = meta_content(soup, "og:description")

    prices = extract_prices_near(text, anchor=name[:30])
    price, original_price = current_and_original(prices)
    disc_pct = discount_percentage(price, original_price)

    if category_hint and not matches_category(name, description, category_hint):
        raise ScraperError(
            f"'{name}' doesn't contain any {category_hint}-related keyword in its name or "
            f"description -- this link almost certainly came from a sitewide navigation/"
            f"recommendation widget on the category page, not the actual product grid. "
            f"Skipping rather than mislabeling it: {url}"
        )

    return ScrapedProduct(
        source=source_name,
        brand=brand,
        category=category_hint or "unknown",
        subcategory=None,
        product_name=name,
        product_code=_code_from_url(url),
        product_url=url,
        image_url=main_image,
        additional_image_urls=[],
        price=price,
        currency=currency,
        original_price=original_price,
        discount_price=price if original_price else None,
        discount_percentage=disc_pct,
        description=description,
        material=None,
        sizes=[],
        colors=[],
        availability="in_stock",
    )


def _code_from_url(url: str) -> Optional[str]:
    """Falls back to the last numeric/alphanumeric path segment as a
    pseudo product code when a site has no cleaner identifier."""
    m = re.search(r"(\d{5,})(?:[/?#]|$)", url)
    if m:
        return m.group(1)
    segments = [s for s in url.rstrip("/").split("/") if s]
    return segments[-1] if segments else None