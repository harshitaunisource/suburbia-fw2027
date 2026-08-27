"""
Suggests real, already-scraped competitor products that match a given
opportunity's concept -- so a buyer catalogue entry can be built in one
click ("take the closest competitor product") instead of typing a new
product by hand.

DESIGN NOTE -- no database migration needed: ProductOpportunity only
stores a human-readable `concept_name` (e.g. "Oversized Sweater"), not
the underlying (attribute_field, attribute_value) pair it was generated
from. Rather than adding new columns to an already-populated table
(which would require a migration step and risk the real scraped data
you already have), this reverse-parses concept_name back into the
attribute value using the exact same construction rule used to build it
in opportunity.py (`value.replace('_', ' ').title()` + category noun).
This is intentionally low-risk over "correct-by-construction" -- it
avoids touching the schema of a table you already have real data in.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Product, ProductAttributes, ProductOpportunity
from app.services.opportunity import CATEGORY_NOUN, CONCEPT_FIELDS


def _reverse_parse_concept_value(concept_name: str, category: str) -> str:
    """Inverse of opportunity.py's concept_name construction:
    f"{value.replace('_', ' ').title()} {noun}" -> value
    """
    noun = CATEGORY_NOUN.get(category, category.capitalize())
    suffix = f" {noun}"
    title_value = concept_name[: -len(suffix)] if concept_name.endswith(suffix) else concept_name
    return title_value.lower().replace(" ", "_")


def get_suggested_products(db: Session, opportunity: ProductOpportunity, limit: int = 8) -> list[Product]:
    """Returns real competitor Products (never Suburbia's own) whose
    attributes match this opportunity's concept, best candidates first
    (has a locally-downloaded image > has any image > has a price)."""
    value = _reverse_parse_concept_value(opportunity.concept_name, opportunity.category)

    # The value could originally have come from any one of these
    # attribute fields (fit, pattern, neckline, sleeve_type, fabric_type,
    # style) -- search all of them, since the vocab barely overlaps
    # across fields in practice (e.g. "oversized" only ever appears as a
    # fit value, "stripe" only as a pattern value).
    field_conditions = [getattr(ProductAttributes, f) == value for f in CONCEPT_FIELDS]

    query = (
        db.query(Product)
        .join(ProductAttributes, ProductAttributes.product_id == Product.id)
        .filter(
            Product.category == opportunity.category,
            Product.source != "suburbia",
            or_(*field_conditions),
        )
    )

    products = query.all()

    # Rank without extra SQL complexity: real local image first (best for
    # the catalogue), then has at least a hotlinked image_url, then price
    # known -- ties broken by most-recently-scraped.
    def sort_key(p: Product):
        return (
            0 if p.local_image_path else 1,
            0 if p.image_url else 1,
            0 if p.price else 1,
            -(p.scraped_at.timestamp() if p.scraped_at else 0),
        )

    products.sort(key=sort_key)
    return products[:limit]