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


def run_attribute_extraction(db: Session, limit: int = 500, category: str | None = None) -> dict:
    provider = get_ai_provider()

    def _unprocessed_query():
        q = db.query(Product).outerjoin(ProductAttributes).filter(ProductAttributes.id.is_(None))
        if category:
            q = q.filter(Product.category == category)
        return q

    products = _unprocessed_query().limit(limit).all()

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
            attrs = ProductAttributes(product_id=product.id)
            for field in ATTRIBUTE_FIELDS:
                setattr(attrs, field, result.get(field, "unknown"))
            attrs.ai_confidence = result.get("confidence", 0.0)
            db.add(attrs)
            processed += 1
        except Exception:
            failed += 1
            continue

    db.commit()
    return {
        "provider": provider.name,
        "category": category or "all",
        "processed": processed,
        "failed": failed,
        # BUG FIX: this previously counted unprocessed products across
        # ALL categories regardless of the `category` filter passed in,
        # which made "remaining_unprocessed: 243" print immediately after
        # finishing all 225 sweaters -- that 243 was actually the blouse
        # count waiting in the next loop iteration, not a real problem
        # with sweaters. Now correctly scoped to match what was just run.
        "remaining_unprocessed_in_this_category": _unprocessed_query().count(),
    }