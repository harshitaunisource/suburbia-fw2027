"""
Phase 5: AI product attribute extraction (spec section 9).

Runs the active AI provider (see app/services/ai/factory.py) over
products that don't have attributes yet, writing one ProductAttributes
row per product. Never crashes the whole batch on one bad product/AI
call -- logs and continues, same defensive pattern as the scrapers.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Product, ProductAttributes
from app.services.ai.base import ATTRIBUTE_FIELDS
from app.services.ai.factory import get_ai_provider


def run_attribute_extraction(
    db: Session, limit: int = 500, category: str | None = None, force: bool = False
) -> dict:
    """
    force=False (default): only processes products with NO attributes
    row yet -- the normal, cheap incremental behavior.

    force=True: reprocesses EVERY matching product, even ones that
    already have attributes -- existing rows are updated in place
    (never duplicated; product_id is unique on ProductAttributes) rather
    than skipped. Needed whenever you change AI_PROVIDER (e.g. mock ->
    openai/anthropic) and want previously-processed products to actually
    pick up the new provider's results -- without this, switching
    providers silently does nothing for anything already processed,
    since by definition those products no longer look "unprocessed".
    """
    provider = get_ai_provider()

    def _query():
        q = db.query(Product)
        if not force:
            q = q.outerjoin(ProductAttributes).filter(ProductAttributes.id.is_(None))
        if category:
            q = q.filter(Product.category == category)
        return q

    products = _query().limit(limit).all()

    processed = 0
    failed = 0

    for product in products:
        try:
            result = provider.extract_attributes(
                product_name=product.product_name,
                description=product.description,
                category=product.category or "unknown",
                image_path=product.local_image_path,
            )
            attrs = (
                db.query(ProductAttributes)
                .filter(ProductAttributes.product_id == product.id)
                .first()
            )
            if not attrs:
                attrs = ProductAttributes(product_id=product.id)
                db.add(attrs)
            for field in ATTRIBUTE_FIELDS:
                setattr(attrs, field, result.get(field, "unknown"))
            attrs.ai_confidence = result.get("confidence", 0.0)
            processed += 1
        except Exception:
            failed += 1
            continue

    db.commit()

    def _unprocessed_query():
        q = db.query(Product).outerjoin(ProductAttributes).filter(ProductAttributes.id.is_(None))
        if category:
            q = q.filter(Product.category == category)
        return q

    return {
        "provider": provider.name,
        "category": category or "all",
        "force": force,
        "processed": processed,
        "failed": failed,
        # Scoped to match what was just run, not the whole database --
        # see the BUG FIX note this replaced for why that distinction
        # matters.
        "remaining_unprocessed_in_this_category": _unprocessed_query().count(),
    }