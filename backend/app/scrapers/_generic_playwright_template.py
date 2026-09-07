"""
Generic, reusable parsing helpers shared by the Playwright-based scrapers
whose product pages mostly expose standard e-commerce signals.

UPDATED ARCHITECTURE (no AI/LLM anywhere in this file):
Extraction now tries THREE layers in order, cheapest/most-reliable
first, instead of jumping straight to og:title/regex scanning:

  1. Structured data (JSON-LD Product / microdata / Open Graph
     e-commerce meta) -- see structured_data.py. When a site embeds
     this (most modern storefronts do, for Google's benefit), it's
     deterministic and doesn't depend on guessing.
  2. Domain-specific overrides (DOMAIN_OVERRIDES below) -- for the
     handful of real sites confirmed via debug HTML to need a specific
     CSS selector/wait-time/title-cleaning rule. Still not AI; this is
     the same mechanism as before, kept because it's cheap and some
     sites genuinely need it.
  3. Generic heuristic fallback (og:title / <h1> / anchored price scan)
     -- the original behavior, now only reached when layers 1 and 2
     both come up empty.

Currency is now DETECTED from the page (symbol/ISO-code/locale via
currency_detect.py) rather than trusted from a manually-typed form
field -- the configured value is only used as the final fallback.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.scrapers._price_utils import current_and_original, discount_percentage, extract_prices_near
from app.scrapers.base import ScrapedProduct
from app.scrapers.currency_detect import detect_currency
from app.scrapers.playwright_base import ScraperError
from app.scrapers.structured_data import extract_structured_product

# Known site-specific quirks that break the standard OpenGraph-based
# parsing below -- confirmed via real inspection (debug HTML dumps),
# never guessed. Keyed by domain so ANY caller gets the fix
# automatically. This layer runs AFTER structured-data extraction has
# already been tried and failed for a given page -- a site with good
# JSON-LD never reaches this at all.
DOMAIN_OVERRIDES = {
    "bo.textilon.com": {
        "title_selector": "div.producto_.text-3xl",
        "skip_description": True,
        "wait_ms": 8000,
        "title_separators": ("|",),
        # Confirmed live 2026-09-07: the category page's product grid
        # is populated by client-side rendering that finishes AFTER the
        # network itself goes idle (the page's own "Cargando..." spinner
        # with class "ant-spin-spinning" is still present even once
        # wait_until="networkidle" has already fired -- the pagination
        # count loads first, the actual product cards render some time
        # after). Waiting for this selector to become hidden is a direct
        # signal tied to the real thing we care about, instead of an
        # indirect inference from network timing.
        "category_wait_selector_hidden": ".ant-spin-spinning",
        # Only Textilon gets networkidle -- see category_wait_until_for's
        # docstring for why this must stay opt-in, not the default.
        "category_wait_until": "networkidle",
    },
}


def domain_of(url: str) -> str:
    return urlparse(url).netloc


def wait_selector_for(url: str, default: str = "h1") -> str:
    override = DOMAIN_OVERRIDES.get(domain_of(url))
    if override and override.get("title_selector"):
        return override["title_selector"]
    return default


def wait_ms_for(url: str, default: int) -> int:
    override = DOMAIN_OVERRIDES.get(domain_of(url))
    if override and override.get("wait_ms"):
        return max(default, override["wait_ms"])
    return default


def category_wait_until_for(url: str, default: str = "domcontentloaded") -> str:
    """Navigation-completion condition for the CATEGORY page fetch --
    see wait_until's docstring in playwright_base.py. "domcontentloaded"
    (Playwright's own default, fast) is correct for the vast majority of
    sites. "networkidle" is ONLY set here for domains confirmed to need
    it (client-rendered SPAs whose product grid loads after an async API
    call) -- it must stay opt-in, not the default, because it waits for
    a full 500ms of ZERO network activity, which many ordinary sites
    (analytics beacons, chat widgets, lazy-load polling) never actually
    reach, causing a hang all the way to the 30s timeout even once the
    real content has long since rendered. Confirmed live: making
    networkidle the default broke a normal Shopify-style site
    (sundaratextiles.com) that had nothing to do with the SPA problem it
    was meant to fix.
    """
    override = DOMAIN_OVERRIDES.get(domain_of(url))
    if override and override.get("category_wait_until"):
        return override["category_wait_until"]
    return default


def category_wait_hidden_for(url: str) -> Optional[str]:
    """CSS selector (e.g. a loading spinner) to wait to DISAPPEAR before
    treating a CATEGORY page as ready -- see the wait_selector_hidden
    docstring in playwright_base.py for why this exists as a separate
    mechanism from wait_until="networkidle"."""
    override = DOMAIN_OVERRIDES.get(domain_of(url))
    if override:
        return override.get("category_wait_selector_hidden")
    return None


def strip_model_details(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    cleaned = re.sub(r"Model (?:height|is)[^.]*\.?", "", text, flags=re.IGNORECASE)
    return cleaned.strip() or None


def meta_content(soup: BeautifulSoup, prop: str) -> Optional[str]:
    el = soup.select_one(f"meta[property='{prop}']") or soup.select_one(f"meta[name='{prop}']")
    return el["content"].strip() if el and el.get("content") else None


PLACEHOLDER_IMAGE_MARKERS = ["no-image", "placeholder", "default-image", "noimage"]


def extract_jsonld_image(soup: BeautifulSoup) -> Optional[str]:
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
    if not title:
        return None
    for sep in separators:
        if sep in title:
            return title.split(sep)[0].strip()
    return title.strip()


# Backstop against link-discovery grabbing an unrelated widget/nav link
# from the category page (confirmed real: a patio-furniture link
# scraped as if it were a blouse). If a scraped product's own name/
# description doesn't contain any word plausibly related to its claimed
# category, something went wrong upstream -- reject rather than
# mislabel.
CATEGORY_SANITY_KEYWORDS = {
    "sweaters": [
        "sweater", "cardigan", "jumper", "knit", "pullover", "sweatshirt",
        "suéter", "sueter", "cárdigan", "cardigán", "tejido", "punto",
    ],
    "blouses": [
        "blouse", "shirt", "top", "tunic", "tank", "camisole",
        "blusa", "camisa", "playera", "top", "tunica", "túnica",
    ],
    "pajamas": [
        "pajama", "pajamas", "pyjama", "pyjamas", "sleepwear", "nightwear",
        "pijama", "pijamas", "piyama", "piyamas", "camison", "camisón",
    ],
}


def keywords_match(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(kw.strip().lower())}\b", lowered) for kw in keywords if kw.strip())


def matches_category(name: str, description: Optional[str], category: Optional[str]) -> bool:
    keywords = CATEGORY_SANITY_KEYWORDS.get(category or "")
    if not keywords:
        return True
    text = f"{name} {description or ''}"
    return keywords_match(text, keywords)


COMPOSITION_RE = re.compile(
    r"((?:\d{1,3}%\s*[A-Za-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+[\s,]*){1,4})", re.IGNORECASE
)


def extract_composition(text: str) -> Optional[str]:
    match = COMPOSITION_RE.search(text)
    if match:
        return match.group(1).strip().rstrip(",")
    return None


def _html_lang(soup: BeautifulSoup) -> Optional[str]:
    html_tag = soup.find("html")
    return html_tag.get("lang") if html_tag else None


def parse_generic_product(
    html: str,
    url: str,
    source_name: str,
    brand: Optional[str],
    category_hint: Optional[str],
    currency: str = "MXN",
    title_separators: tuple[str, ...] = ("|", " - "),
) -> ScrapedProduct:
    """Product-page parse. Tries structured data first (deterministic,
    no guessing), then domain overrides + heuristic fallback. `currency`
    is now only the LAST-RESORT fallback value -- the real currency is
    detected from the page itself whenever possible.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    override = DOMAIN_OVERRIDES.get(domain_of(url))

    # ---- Layer 1: structured data (JSON-LD / microdata / OpenGraph) ----
    structured = extract_structured_product(html)

    name = structured.name if structured else None
    main_image = structured.image_url if structured else None
    description = structured.description if structured else None
    price = structured.price if structured else None
    detected_currency = structured.currency if structured else None
    material = structured.material if structured else None
    color = structured.color if structured else None

    # ---- Layer 2: domain overrides for the title, if structured data
    # didn't already give us a name (a confirmed-broken domain never
    # has usable structured data for its title either, in practice).
    if not name and override and override.get("title_selector"):
        title_el = soup.select_one(override["title_selector"])
        name = title_el.get_text(strip=True) if title_el else None

    # ---- Layer 3: generic heuristic fallback ----
    if not name:
        name = meta_content(soup, "og:title")
    if not name:
        h1 = soup.select_one("h1")
        name = h1.get_text(strip=True) if h1 else None
    effective_separators = (override.get("title_separators") if override else None) or title_separators
    name = clean_title(name, effective_separators)

    if not name:
        raise ScraperError(
            f"Could not find a product name (structured data, og:title, or <h1>) for {url} -- "
            "page may not have rendered, or structure differs from expected."
        )

    if not main_image:
        main_image = meta_content(soup, "og:image")
    if not main_image or any(marker in main_image.lower() for marker in PLACEHOLDER_IMAGE_MARKERS):
        jsonld_image = extract_jsonld_image(soup)
        if jsonld_image:
            main_image = jsonld_image

    if description is None and not (override and override.get("skip_description")):
        description = meta_content(soup, "og:description")

    price_text_for_currency = text
    if price is None:
        prices = extract_prices_near(text, anchor=name[:30])
        price, original_price = current_and_original(prices)
    else:
        # Structured data already gave us a clean numeric price -- still
        # scan the surrounding text once for an ORIGINAL (pre-discount)
        # price, since JSON-LD `offers.price` is usually just the
        # current price with no separate "was" value.
        prices = extract_prices_near(text, anchor=name[:30])
        _, original_price = current_and_original(prices)
        if original_price is not None and original_price <= price:
            original_price = None

    disc_pct = discount_percentage(price, original_price)

    if not material:
        material = extract_composition(text)

    # ---- Currency: page-derived first, configured value only as the
    # final fallback (this replaces trusting the form dropdown outright).
    resolved_currency = detected_currency or detect_currency(
        price_text=price_text_for_currency,
        url=url,
        html_lang=_html_lang(soup),
        fallback=currency,
    )

    if category_hint and not matches_category(name, description, category_hint):
        raise ScraperError(
            f"'{name}' doesn't contain any {category_hint}-related keyword in its name or "
            f"description -- this link almost certainly came from a sitewide navigation/"
            f"recommendation widget, not the actual product grid. Skipping: {url}"
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
        currency=resolved_currency,
        original_price=original_price,
        discount_price=price if original_price else None,
        discount_percentage=disc_pct,
        description=description,
        material=material,
        sizes=[],
        colors=[color] if color else [],
        availability=(structured.availability if structured else None) or "in_stock",
    )


def _code_from_url(url: str) -> Optional[str]:
    m = re.search(r"(\d{5,})(?:[/?#]|$)", url)
    if m:
        return m.group(1)
    segments = [s for s in url.rstrip("/").split("/") if s]
    return segments[-1] if segments else None