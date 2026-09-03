"""
Phase 6: Market Analytics (spec section 10).

Pure read/aggregation functions over the products + product_attributes
tables -- no scoring or opinions here, just counts and distributions,
filterable by category / brand / a list of sources.

`sources` (2026-09-03) replaces the old fixed "suburbia / competitors /
all" `group` param as the primary way to scope these charts: pass any
list of Product.source values (e.g. ["suburbia", "zara", "hm"]) and
every function below filters to exactly those, however many brands that
is. This is what lets the Market Analytics page offer a live,
ever-growing multi-select of brands instead of three hardcoded options
-- the list of brands available IS whatever the `source` column
currently contains, which grows on its own as new categories/brands get
scraped (see GET /api/products/meta/sources).

`group` ("suburbia" | "competitors") is kept working for any old caller
that still passes it, but is ignored whenever `sources` is given.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Product, ProductAttributes
from app.services.pricing import compute_mrp


def _apply_source_filter(q, sources: Optional[list[str]], group: Optional[str]):
    if sources:
        return q.filter(Product.source.in_(sources))
    if group == "suburbia":
        return q.filter(Product.source == "suburbia")
    elif group == "competitors":
        return q.filter(Product.source != "suburbia")
    return q


def _base_query(
    db: Session,
    category: Optional[str],
    brand: Optional[str],
    group: Optional[str],
    sources: Optional[list[str]] = None,
):
    q = db.query(Product)
    if category:
        q = q.filter(Product.category == category)
    if brand:
        q = q.filter(Product.brand == brand)
    q = _apply_source_filter(q, sources, group)
    return q


def product_counts(db: Session, category: Optional[str] = None, sources: Optional[list[str]] = None) -> dict:
    q = db.query(Product.source, func.count(Product.id)).group_by(Product.source)
    if category:
        q = q.filter(Product.category == category)
    if sources:
        q = q.filter(Product.source.in_(sources))
    by_brand = {source: count for source, count in q.all()}

    q2 = db.query(Product.category, func.count(Product.id)).group_by(Product.category)
    if sources:
        q2 = q2.filter(Product.source.in_(sources))
    by_category = {cat or "unknown": count for cat, count in q2.all()}

    return {"by_source": by_brand, "by_category": by_category}


def price_distribution(
    db: Session,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    group: Optional[str] = None,
    sources: Optional[list[str]] = None,
) -> dict:
    """Returns price stats GROUPED BY CURRENCY, never blended across
    currencies -- e.g. {"MXN": {...}, "USD": {...}}, not one combined
    set of numbers. Blending raw numbers from different currencies
    together (confirmed live: MXN and USD values averaged as if they
    were the same unit) produces meaningless min/avg/max. This does NOT
    apply any currency-conversion rate to normalize them into one
    number either -- a made-up or stale exchange rate would just
    replace one wrong number with a different wrong number. If a single
    combined figure is ever needed, that requires a real, current FX
    rate source, which this project does not have wired up.

    Also uses MRP (original list price), never a discounted/sale price:
    Product.original_price when the item is on sale, falling back to
    Product.price only when there's no discount at all (in which case
    price already IS the MRP).

    "avg" is the plain arithmetic mean of every included product's MRP
    (sum / count) -- NOT (min + max) / 2. "median" was intentionally
    removed per explicit request -- only min/avg/max/count are returned
    per currency.
    """
    q = _base_query(db, category, brand, group, sources).filter(Product.price.isnot(None))
    products = q.all()

    by_currency: dict[str, list[float]] = {}
    for p in products:
        currency = p.currency or "USD"
        mrp = compute_mrp(p.price, p.original_price)
        if mrp is None:
            continue
        by_currency.setdefault(currency, []).append(mrp)

    result = {}
    for currency, prices in by_currency.items():
        result[currency] = {
            "min": round(min(prices), 2),
            "avg": round(sum(prices) / len(prices), 2),
            "max": round(max(prices), 2),
            "count": len(prices),
        }
    return result


def _attribute_distribution(
    db: Session,
    field: str,
    category: Optional[str],
    brand: Optional[str],
    group: Optional[str],
    sources: Optional[list[str]] = None,
) -> list[dict]:
    column = getattr(ProductAttributes, field)
    q = (
        db.query(column, func.count(ProductAttributes.id))
        .join(Product, Product.id == ProductAttributes.product_id)
        .filter(column.isnot(None), column != "unknown")
    )
    if category:
        q = q.filter(Product.category == category)
    if brand:
        q = q.filter(Product.brand == brand)
    q = _apply_source_filter(q, sources, group)

    rows = q.group_by(column).order_by(func.count(ProductAttributes.id).desc()).all()
    return [{"value": value, "count": count} for value, count in rows]


def color_analysis(db: Session, **filters) -> list[dict]:
    return _attribute_distribution(db, "primary_color", **filters)


def silhouette_analysis(db: Session, **filters) -> list[dict]:
    return _attribute_distribution(db, "fit", **filters)  # fit doubles as silhouette bucket in the mock provider


def pattern_analysis(db: Session, **filters) -> list[dict]:
    return _attribute_distribution(db, "pattern", **filters)


def neckline_analysis(db: Session, **filters) -> list[dict]:
    return _attribute_distribution(db, "neckline", **filters)


def full_report(
    db: Session,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    group: Optional[str] = None,
    sources: Optional[list[str]] = None,
) -> dict:
    filters = {"category": category, "brand": brand, "group": group, "sources": sources}
    return {
        "product_counts": product_counts(db, category, sources),
        "price_distribution": price_distribution(db, **filters),
        "colors": color_analysis(db, **filters),
        "silhouettes": silhouette_analysis(db, **filters),
        "patterns": pattern_analysis(db, **filters),
        "necklines": neckline_analysis(db, **filters),
    }