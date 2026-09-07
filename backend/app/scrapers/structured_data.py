"""
Structured-data product extraction -- NO AI/LLM. Pure parsing of the
machine-readable data most e-commerce sites already embed for Google:

  1. JSON-LD `@type: Product` (schema.org) -- highest confidence,
     because the site declared these exact fields on purpose.
  2. Microdata (`itemscope itemtype=".../Product"` + `itemprop=...`)
     -- same schema.org vocabulary, older/alternate syntax.
  3. Open Graph e-commerce extension (`product:price:amount`,
     `product:price:currency`, `og:image`, `og:title`) -- almost every
     modern storefront has at least this much, even without full
     schema.org markup.

This is tried FIRST, before any heuristic/regex scanning of the visible
page text (see _generic_playwright_template.py) -- when it succeeds,
the result is deterministic and doesn't depend on guessing which piece
of text on the page happens to be the price.

Returns `None` (never a partial guess) when none of the three sources
yields at least a name -- callers fall back to heuristic extraction.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup


@dataclass
class StructuredProduct:
    name: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    material: Optional[str] = None  # from JSON-LD `material`/`additionalProperty`
    color: Optional[str] = None     # from JSON-LD `color`
    sku: Optional[str] = None
    availability: Optional[str] = None
    source: str = ""  # "jsonld" | "microdata" | "opengraph" -- for logging/debugging only


def _first_number(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.search(r"[\d,]+\.?\d*", value.replace(",", ""))
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _flatten_offers(offers) -> list[dict]:
    """schema.org `offers` can be a single object, a list, or an
    `AggregateOffer` wrapping a `lowPrice`/`highPrice` -- normalize all
    three shapes into a flat list of plain dicts."""
    if offers is None:
        return []
    if isinstance(offers, dict):
        offers = [offers]
    if not isinstance(offers, list):
        return []
    return [o for o in offers if isinstance(o, dict)]


def _from_jsonld_block(data: dict) -> Optional[StructuredProduct]:
    if data.get("@type") not in ("Product", ["Product"]) and "Product" not in str(data.get("@type", "")):
        return None

    name = data.get("name")
    description = data.get("description")

    image = data.get("image")
    if isinstance(image, list) and image:
        image = image[0]
    if isinstance(image, dict):
        image = image.get("url")

    price = currency = availability = sku = None
    for offer in _flatten_offers(data.get("offers")):
        price = price or _first_number(offer.get("price") or offer.get("lowPrice"))
        currency = currency or offer.get("priceCurrency")
        availability = availability or offer.get("availability")
        sku = sku or offer.get("sku") or data.get("sku")

    color = data.get("color")
    if isinstance(color, list):
        color = ", ".join(str(c) for c in color)

    material = data.get("material")
    if isinstance(material, list):
        material = ", ".join(str(m) for m in material)
    if not material:
        # Composition is sometimes carried as an `additionalProperty`
        # entry (PropertyValue) rather than the top-level `material`
        # field -- check there too before giving up.
        for prop in data.get("additionalProperty") or []:
            if isinstance(prop, dict) and str(prop.get("name", "")).lower() in (
                "material", "composition", "fabric",
            ):
                material = prop.get("value")
                break

    if not name:
        return None

    return StructuredProduct(
        name=str(name).strip(),
        price=price,
        currency=str(currency).strip().upper() if currency else None,
        image_url=image if isinstance(image, str) else None,
        description=str(description).strip() if description else None,
        material=str(material).strip() if material else None,
        color=str(color).strip() if color else None,
        sku=str(sku) if sku else None,
        availability=str(availability).split("/")[-1] if availability else None,
        source="jsonld",
    )


def extract_jsonld_product(soup: BeautifulSoup) -> Optional[StructuredProduct]:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue

        candidates = data if isinstance(data, list) else [data]
        # `@graph` wrapper (common in WordPress/Yoast-style SEO plugins).
        for item in list(candidates):
            if isinstance(item, dict) and "@graph" in item:
                candidates.extend(item["@graph"])

        for item in candidates:
            if not isinstance(item, dict):
                continue
            result = _from_jsonld_block(item)
            if result:
                return result
    return None


def extract_microdata_product(soup: BeautifulSoup) -> Optional[StructuredProduct]:
    """Older/alternate schema.org syntax: itemscope/itemtype attributes
    instead of a JSON-LD script block. Same vocabulary, different
    plumbing -- some sites (especially older Shopify/Magento themes)
    only implement this form."""
    scope = soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)})
    if not scope:
        return None

    def prop(name: str) -> Optional[str]:
        el = scope.find(attrs={"itemprop": name})
        if not el:
            return None
        return el.get("content") or el.get("href") or el.get_text(strip=True)

    name = prop("name")
    if not name:
        return None

    price = _first_number(prop("price") or prop("lowPrice"))
    currency = prop("priceCurrency")
    image = prop("image")

    return StructuredProduct(
        name=name.strip(),
        price=price,
        currency=currency.strip().upper() if currency else None,
        image_url=image,
        description=(prop("description") or "").strip() or None,
        color=(prop("color") or "").strip() or None,
        material=(prop("material") or "").strip() or None,
        sku=prop("sku"),
        availability=(prop("availability") or "").split("/")[-1] or None,
        source="microdata",
    )


def _meta(soup: BeautifulSoup, prop: str) -> Optional[str]:
    el = soup.select_one(f"meta[property='{prop}']") or soup.select_one(f"meta[name='{prop}']")
    return el["content"].strip() if el and el.get("content") else None


def extract_opengraph_product(soup: BeautifulSoup) -> Optional[StructuredProduct]:
    """Open Graph's e-commerce extension -- lower confidence than
    JSON-LD/microdata (no color/material/sku), but present on far more
    sites since og:title/og:image are near-universal for link previews.
    """
    name = _meta(soup, "og:title")
    if not name:
        return None

    price = _first_number(_meta(soup, "product:price:amount") or _meta(soup, "og:price:amount"))
    currency = _meta(soup, "product:price:currency") or _meta(soup, "og:price:currency")
    image = _meta(soup, "og:image")
    availability = _meta(soup, "product:availability")

    return StructuredProduct(
        name=name.strip(),
        price=price,
        currency=currency.strip().upper() if currency else None,
        image_url=image,
        description=(_meta(soup, "og:description") or "").strip() or None,
        availability=availability,
        source="opengraph",
    )


def extract_structured_product(html: str) -> Optional[StructuredProduct]:
    """Tries all three structured-data sources in priority order and
    returns the first one that yields at least a product name. Merges
    in fields a higher-priority source left empty from a lower-priority
    one when both are present (e.g. JSON-LD has no image but Open
    Graph's og:image does) -- never overwrites a field a higher-priority
    source already filled in.
    """
    soup = BeautifulSoup(html, "html.parser")

    candidates = [
        extract_jsonld_product(soup),
        extract_microdata_product(soup),
        extract_opengraph_product(soup),
    ]
    candidates = [c for c in candidates if c is not None]
    if not candidates:
        return None

    best = candidates[0]
    for other in candidates[1:]:
        for field_name in (
            "price", "currency", "image_url", "description",
            "material", "color", "sku", "availability",
        ):
            if getattr(best, field_name) is None and getattr(other, field_name) is not None:
                setattr(best, field_name, getattr(other, field_name))
    return best