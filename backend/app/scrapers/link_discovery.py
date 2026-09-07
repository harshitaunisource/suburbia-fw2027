"""
Multi-strategy product-link discovery from a category/listing page --
NO AI/LLM. Replaces relying on a single hand-tuned regex
(GenericSourceConfig.pdp_link_pattern) as the only way to find product
links, which is exactly the "manually tune per website" problem this
was built to get rid of.

Strategies are tried in order, cheapest/most-reliable first, and the
first one that returns a plausible number of links wins:

  1. JSON-LD `ItemList` / `CollectionPage.mainEntity` -- when a category
     page embeds this (common on modern storefronts, for the same SEO
     reasons product pages embed `Product` JSON-LD), it lists the exact
     product URLs directly. No pattern-matching needed at all.

  2. Structural URL-pattern clustering -- look at every link on the
     page, group them by a normalized "shape" (numbers/slugs replaced
     with a placeholder), and treat any shape that repeats often enough
     as a real product-grid pattern. This is the actual fix for "an
     arbitrary, never-seen-before website": a product listing grid
     reliably produces MANY links that all share the same URL shape
     (e.g. /products/slug-1234, /products/slug-5678), while nav/filter/
     recommendation links don't repeat that way. No hand-written regex
     needed per site.

  3. A configured override (`GenericSourceConfig.pdp_link_pattern`) --
     kept as an explicit escape hatch for the rare real site that needs
     one, not as the primary mechanism.

  4. The old generic default regex -- last resort.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# Same shape as generic_scraper.py's old DEFAULT_PDP_LINK_PATTERN --
# kept only as the final fallback, not the primary strategy anymore.
DEFAULT_PDP_LINK_PATTERN = r'href="([^"]*(?:/product/|/p/|/dp/|-p-\d+)[^"]*)"'

# Path segments that are almost never part of a real product URL --
# used to discard obvious non-product links before clustering, so they
# don't pollute the pattern-frequency count.
NAV_PATH_MARKERS = (
    "/cart", "/checkout", "/account", "/login", "/signin", "/register",
    "/wishlist", "/search", "/help", "/faq", "/about", "/contact",
    "/privacy", "/terms", "/careers", "/blog", "/newsletter",
    "/customer-service", "/store-locator", "/gift-card",
)

MIN_CLUSTER_SIZE = 4  # a real product grid has more than a handful of items


def _normalize_shape(path: str) -> str:
    """Collapses a URL path into a comparable 'shape': digits become
    '#', and long alphanumeric slugs (product names/SKUs) become '*',
    so /products/blue-sweater-1234 and /products/red-jacket-5678 both
    normalize to /products/*-#, letting them cluster together even
    though their literal text differs."""
    segments = path.strip("/").split("/")
    normalized = []
    for seg in segments:
        seg = re.sub(r"\d+", "#", seg)
        if len(seg) > 3 and any(c.isalpha() for c in seg):
            seg = "*"
        normalized.append(seg)
    return "/" + "/".join(normalized)


def _looks_like_nav(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in NAV_PATH_MARKERS)


def discover_via_jsonld(html: str, base_url: str) -> list[str]:
    """Strategy 1: a category page's own JSON-LD ItemList, when present
    -- the site already tells us exactly which URLs are products."""
    import json as _json

    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
        except Exception:
            continue
        blocks = data if isinstance(data, list) else [data]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            # block.get("mainEntity") is sometimes a plain LIST of
            # Product entities directly (confirmed live on GymShark's
            # Shopify theme), not always wrapped in an ItemList object.
            # Calling .get() on that list crashed with
            # "'list' object has no attribute 'get'" -- guard by type
            # instead of assuming mainEntity is always a dict.
            items = block.get("itemListElement")
            if not items:
                main_entity = block.get("mainEntity")
                if isinstance(main_entity, dict):
                    items = main_entity.get("itemListElement")
                elif isinstance(main_entity, list):
                    items = main_entity
            if not items:
                continue
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                url = entry.get("url")
                if not url and isinstance(entry.get("item"), dict):
                    url = entry["item"].get("url") or entry["item"].get("@id")
                if url:
                    urls.append(urljoin(base_url, url))
    return sorted(set(urls))


def discover_via_structural_clustering(html: str, base_url: str) -> list[str]:
    """Strategy 2: group every link on the page by normalized URL
    shape; return the links belonging to whichever shape repeats often
    enough to plausibly be a product grid. This is the general-purpose
    replacement for a hand-written per-site regex."""
    soup = BeautifulSoup(html, "html.parser")
    base_netloc = urlparse(base_url).netloc
    base_path_segments = [s for s in urlparse(base_url).path.strip("/").split("/") if s]

    by_shape: dict[str, list[str]] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc and parsed.netloc != base_netloc:
            continue  # off-site link (social share, ad, etc.)
        if _looks_like_nav(parsed.path):
            continue
        if parsed.path in ("", "/"):
            continue
        segments = [s for s in parsed.path.strip("/").split("/") if s]
        # Require at least 2 path segments. Real product detail pages
        # are almost always nested below a category/product prefix
        # (/product/slug, /p/12345, /articulos/producto/...). Nav and
        # footer links are almost always a single bare segment
        # (/carrito, /tiendas, /usuario, /about) -- and critically,
        # EVERY such single-segment path normalizes to the same shape
        # "/*" regardless of language, so a site's entire nav/footer
        # menu can cluster together into one dominant fake "product
        # grid" that out-competes the real (often sparser) one.
        # Confirmed live: bo.textilon.com's /carrito, /hombre/,
        # /libro_reclamaciones, /politicas_privacidad,
        # /preguntas_frecuentes, /tiendas, /usuario all collapsed to
        # "/*" and were picked as the "product" cluster, wasting ~30s
        # per dead link on real fetch timeouts.
        if len(segments) < 2:
            continue
        # Exclude "siblings" of the category page itself -- a link at
        # the SAME depth as the category URL that shares every segment
        # except the last one is almost always another item in the
        # same nav/subcategory menu (e.g. category URL
        # .../subcategoria/camisetas and a sibling link
        # .../subcategoria/pantalones), not a product detail page.
        # Confirmed live: on bo.textilon.com this exact pattern was
        # picked as the "product" cluster -- all 4 links led to generic
        # category-template pages with no product name/price/material,
        # each parsing as the site's default title.
        if len(segments) == len(base_path_segments) and segments[:-1] == base_path_segments[:-1]:
            continue
        shape = _normalize_shape(parsed.path)
        by_shape.setdefault(shape, []).append(full)

    if not by_shape:
        return []

    # Pick the shape(s) with the most repeats. A real product grid
    # dominates the link count on a category page; anything appearing
    # fewer than MIN_CLUSTER_SIZE times is treated as noise (single
    # nav links, footer links, etc. don't repeat this way).
    counts = Counter({shape: len(urls) for shape, urls in by_shape.items()})
    best_shape, best_count = counts.most_common(1)[0]
    if best_count < MIN_CLUSTER_SIZE:
        return []

    return sorted(set(by_shape[best_shape]))


def discover_via_regex(html: str, base_url: str, pattern: str) -> list[str]:
    """Strategy 3/4: a configured or default regex -- kept as an
    explicit fallback, not the primary mechanism."""
    links = sorted(set(re.findall(pattern, html)))
    return [urljoin(base_url, link) for link in links]


def discover_product_links(
    html: str,
    base_url: str,
    configured_pattern: Optional[str] = None,
    max_links: int = 200,
) -> tuple[list[str], str]:
    """Runs every strategy in order and returns (urls, strategy_name)
    for whichever one first produces a plausible result. `strategy_name`
    is included so callers/logs can see which method actually worked
    for a given site -- useful for building confidence in the approach
    without needing per-site debugging.
    """
    jsonld_urls = discover_via_jsonld(html, base_url)
    if len(jsonld_urls) >= MIN_CLUSTER_SIZE:
        return jsonld_urls[:max_links], "jsonld_itemlist"

    structural_urls = discover_via_structural_clustering(html, base_url)
    if structural_urls:
        return structural_urls[:max_links], "structural_clustering"

    if configured_pattern:
        configured_urls = discover_via_regex(html, base_url, configured_pattern)
        if configured_urls:
            return configured_urls[:max_links], "configured_regex"

    default_urls = discover_via_regex(html, base_url, DEFAULT_PDP_LINK_PATTERN)
    return default_urls[:max_links], "default_regex"