"""
Phase 7 + 8: Suburbia vs Market Gap Analysis and Opportunity Scoring
(spec sections 11 and 12).

Everything here is deliberately simple, transparent arithmetic over data
already in the database -- NOT an LLM call, and NOT random numbers (spec
section 12: "Do NOT simply generate random AI scores. Every score must
be explainable."). Each ProductOpportunity row stores a human-readable
`reason` string spelling out exactly which numbers produced its score.

CONCEPT = a (category, attribute_field, attribute_value) triple, e.g.
(sweaters, fit, oversized) -> "Oversized Sweater". This is a simpler
version of spec section 11's example table (which shows single
descriptive concepts like "Oversized sweater", "Striped sweater") --
extending to multi-attribute combinations (e.g. "Oversized Striped
V-Neck Sweater" as in the section 13 example) is a natural next step
once there's enough real attribute data to support it without the
combinations becoming too sparse to be statistically meaningful.

SCORING FORMULA (spec section 12), each component on a 0-100 scale:
  trend_strength       = how many distinct competitor brands carry this
                          concept, as a % of all competitor brands seen
                          in this category (breadth signal).
  competitor_adoption   = this concept's % share of all competitor
                          products in this category (depth signal).
  suburbia_gap          = competitor_adoption_pct - suburbia_penetration_pct,
                          clamped to [0, 100].
  price_opportunity      = how much higher competitors' average price is
                          for this concept vs. Suburbia's average price
                          for the category overall, as a %, clamped to
                          [0, 100]. Positive = competitors charge more,
                          i.e. room to introduce the concept at a
                          competitive-but-profitable price point.
  commercial_potential   = this concept's raw competitor unit count,
                          normalized against the single largest concept's
                          count in this category (volume signal).

  opportunity_score = 0.25*trend + 0.20*competitor_adoption
                     + 0.25*suburbia_gap + 0.15*price_opportunity
                     + 0.15*commercial_potential
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import OpportunityStatus, Product, ProductAttributes, ProductOpportunity

CONCEPT_FIELDS = ["fit", "pattern", "neckline", "sleeve_type", "fabric_type", "style"]

WEIGHTS = {
    "trend_score": 0.25,
    "competitor_score": 0.20,
    "suburbia_gap_score": 0.25,
    "price_score": 0.15,
    "commercial_score": 0.15,
}

CATEGORY_NOUN = {"sweaters": "Sweater", "blouses": "Blouse"}


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def compute_gap_table(db: Session, category: str) -> list[dict]:
    """Returns the raw comparison table for spec section 11
    (Concept / Market % / Suburbia % / Gap) for one category."""
    market_total = (
        db.query(func.count(Product.id))
        .filter(Product.category == category, Product.source != "suburbia")
        .scalar()
        or 0
    )
    suburbia_total = (
        db.query(func.count(Product.id))
        .filter(Product.category == category, Product.source == "suburbia")
        .scalar()
        or 0
    )

    rows = []
    for field in CONCEPT_FIELDS:
        column = getattr(ProductAttributes, field)

        market_counts = (
            db.query(column, func.count(ProductAttributes.id))
            .join(Product, Product.id == ProductAttributes.product_id)
            .filter(Product.category == category, Product.source != "suburbia")
            .filter(column.isnot(None), column != "unknown")
            .group_by(column)
            .all()
        )
        suburbia_counts = dict(
            db.query(column, func.count(ProductAttributes.id))
            .join(Product, Product.id == ProductAttributes.product_id)
            .filter(Product.category == category, Product.source == "suburbia")
            .filter(column.isnot(None), column != "unknown")
            .group_by(column)
            .all()
        )

        for value, m_count in market_counts:
            market_pct = round(100 * m_count / market_total, 1) if market_total else 0.0
            s_count = suburbia_counts.get(value, 0)
            suburbia_pct = round(100 * s_count / suburbia_total, 1) if suburbia_total else 0.0
            gap = round(market_pct - suburbia_pct, 1)
            rows.append(
                {
                    "category": category,
                    "field": field,
                    "value": value,
                    "market_pct": market_pct,
                    "suburbia_pct": suburbia_pct,
                    "gap": gap,
                    "gap_label": "High" if gap >= 20 else "Medium" if gap >= 10 else "Low",
                    "market_count": m_count,
                    "suburbia_count": s_count,
                }
            )

    rows.sort(key=lambda r: r["gap"], reverse=True)
    return rows


def generate_opportunities(db: Session, category: str, top_n: int = 15) -> list[ProductOpportunity]:
    """Phase 8: turns the gap table into scored ProductOpportunity rows.
    Idempotent-ish: re-running replaces previously 'identified' rows for
    this category (never touches shortlisted/selected/rejected/catalogue
    ones, since those reflect a human decision -- see spec section 14)."""
    gap_rows = compute_gap_table(db, category)
    if not gap_rows:
        return []

    max_market_count = max(r["market_count"] for r in gap_rows)

    # brand breadth per concept
    breadth_by_key: dict[tuple, int] = {}
    for field in CONCEPT_FIELDS:
        column = getattr(ProductAttributes, field)
        breadth_rows = (
            db.query(column, func.count(func.distinct(Product.source)))
            .join(Product, Product.id == ProductAttributes.product_id)
            .filter(Product.category == category, Product.source != "suburbia")
            .filter(column.isnot(None), column != "unknown")
            .group_by(column)
            .all()
        )
        for value, brand_count in breadth_rows:
            breadth_by_key[(field, value)] = brand_count

    total_competitor_brands = (
        db.query(func.count(func.distinct(Product.source)))
        .filter(Product.category == category, Product.source != "suburbia")
        .scalar()
        or 1
    )

    suburbia_avg_price = (
        db.query(func.avg(Product.price))
        .filter(Product.category == category, Product.source == "suburbia", Product.price.isnot(None))
        .scalar()
    )

    created: list[ProductOpportunity] = []
    for row in gap_rows[: max(top_n * 2, top_n)]:  # score a bit more than top_n, then trim after sorting
        field, value = row["field"], row["value"]

        trend_score = _clamp(100 * breadth_by_key.get((field, value), 0) / total_competitor_brands)
        competitor_score = _clamp(row["market_pct"])
        suburbia_gap_score = _clamp(row["gap"])
        commercial_score = _clamp(100 * row["market_count"] / max_market_count) if max_market_count else 0.0

        competitor_avg_price = (
            db.query(func.avg(Product.price))
            .join(ProductAttributes, ProductAttributes.product_id == Product.id)
            .filter(
                Product.category == category,
                Product.source != "suburbia",
                Product.price.isnot(None),
                getattr(ProductAttributes, field) == value,
            )
            .scalar()
        )
        if competitor_avg_price and suburbia_avg_price:
            price_score = _clamp(100 * (competitor_avg_price - suburbia_avg_price) / competitor_avg_price)
        else:
            price_score = 0.0  # not enough price data -- explainable as "no data" rather than a guess

        opportunity_score = round(
            trend_score * WEIGHTS["trend_score"]
            + competitor_score * WEIGHTS["competitor_score"]
            + suburbia_gap_score * WEIGHTS["suburbia_gap_score"]
            + price_score * WEIGHTS["price_score"]
            + commercial_score * WEIGHTS["commercial_score"],
            1,
        )

        noun = CATEGORY_NOUN.get(category, category.capitalize())
        concept_name = f"{value.replace('_', ' ').title()} {noun}"

        reason = (
            f"Found in {row['market_count']} competitor products "
            f"({row['market_pct']}% of competitor {category}) across "
            f"{breadth_by_key.get((field, value), 0)}/{total_competitor_brands} competitor brands, "
            f"vs only {row['suburbia_pct']}% of Suburbia's own {category} "
            f"(gap: {row['gap']} pts, {row['gap_label']}). "
            + (
                f"Competitors average {round(competitor_avg_price, 2)} vs Suburbia's "
                f"{round(suburbia_avg_price, 2)} average for this category."
                if competitor_avg_price and suburbia_avg_price
                else "Insufficient price data to compare pricing for this concept."
            )
        )

        created.append(
            ProductOpportunity(
                category=category,
                concept_name=concept_name,
                trend_score=round(trend_score, 1),
                competitor_score=round(competitor_score, 1),
                suburbia_gap_score=round(suburbia_gap_score, 1),
                price_score=round(price_score, 1),
                commercial_score=round(commercial_score, 1),
                opportunity_score=opportunity_score,
                reason=reason,
            )
        )

    created.sort(key=lambda o: o.opportunity_score, reverse=True)
    top = created[:top_n]

    # Replace previously auto-generated ('identified') opportunities for
    # this category only -- never touch ones a human has already acted on.
    db.query(ProductOpportunity).filter(
        ProductOpportunity.category == category, ProductOpportunity.status == OpportunityStatus.identified
    ).delete()
    for opp in top:
        db.add(opp)
    db.commit()
    return top
