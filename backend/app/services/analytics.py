"""
Phase 6: Market Analytics (spec section 10).

Pure read/aggregation functions over the products + product_attributes
tables -- no scoring or opinions here, just counts and distributions,
filterable by category / brand / competitor-vs-suburbia group.
"""
from __future__ import annotations

from statistics import median
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Product, ProductAttributes


def _base_query(db: Session, category: Optional[str], brand: Optional[str], group: Optional[str]):
    q = db.query(Product)
    if category:
        q = q.filter(Product.category == category)
    if brand:
        q = q.filter(Product.brand == brand)
    if group == "suburbia":
        q = q.filter(Product.source == "suburbia")
    elif group == "competitors":
        q = q.filter(Product.source != "suburbia")
    return q


def product_counts(db: Session, category: Optional[str] = None) -> dict:
    q = db.query(Product.source, func.count(Product.id)).group_by(Product.source)
    if category:
        q = q.filter(Product.category == category)
    by_brand = {source: count for source, count in q.all()}

    q2 = db.query(Product.category, func.count(Product.id)).group_by(Product.category)
    by_category = {cat or "unknown": count for cat, count in q2.all()}

    return {"by_source": by_brand, "by_category": by_category}


def price_distribution(
    db: Session, category: Optional[str] = None, brand: Optional[str] = None, group: Optional[str] = None
) -> dict:
    q = _base_query(db, category, brand, group).filter(Product.price.isnot(None))
    prices = [p.price for p in q.all()]
    if not prices:
        return {"min": None, "avg": None, "median": None, "max": None, "count": 0}
    return {
        "min": round(min(prices), 2),
        "avg": round(sum(prices) / len(prices), 2),
        "median": round(median(prices), 2),
        "max": round(max(prices), 2),
        "count": len(prices),
    }


def _attribute_distribution(
    db: Session, field: str, category: Optional[str], brand: Optional[str], group: Optional[str]
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
    if group == "suburbia":
        q = q.filter(Product.source == "suburbia")
    elif group == "competitors":
        q = q.filter(Product.source != "suburbia")

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
    db: Session, category: Optional[str] = None, brand: Optional[str] = None, group: Optional[str] = None
) -> dict:
    filters = {"category": category, "brand": brand, "group": group}
    return {
        "product_counts": product_counts(db, category),
        "price_distribution": price_distribution(db, **filters),
        "colors": color_analysis(db, **filters),
        "silhouettes": silhouette_analysis(db, **filters),
        "patterns": pattern_analysis(db, **filters),
        "necklines": neckline_analysis(db, **filters),
    }
