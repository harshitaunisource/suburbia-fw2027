"""
Matches ONE buyer trend product against your own already-scraped
competitor data (the same `products` table the Products page reads
from -- Asos, C&A, Primark, etc.) -- the "catalogue" half of Trend
Matching. The other half, web search, is app/services/image_search/.

No vector embeddings / ML infra here on purpose: the trend product
already went through the AI vision classifier (vision_classify.py),
producing a short, structured description (name, category, color,
pattern); comparing that directly against each scraped Product's own
name/category/colors with a plain text similarity + exact-attribute
bonus is simple, has zero extra runtime dependency, and is easy to
reason about when a merchant asks "why did it suggest this." If match
quality ever needs to improve beyond this, swapping in a real embedding
similarity search is a contained change to _score_catalogue_match()
below -- nothing about the calling code needs to know the difference.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models import Product, TrendProduct

# Below this, a candidate isn't worth surfacing as a suggested match at
# all -- avoids showing the merchant a wall of near-random "matches" for
# a trend product that genuinely has nothing close to it.
MIN_MATCH_SCORE = 0.25

# Common words that appear in almost every garment name/description and
# so carry near-zero discriminating signal for "is this the same kind of
# product" -- excluded from the word-overlap comparison so two
# completely unrelated items (e.g. a sweater and a blouse) don't score
# artificially high just because both descriptions say "women's" and
# "fit".
_STOPWORDS = {
    "a", "an", "the", "with", "in", "of", "and", "for", "loose", "relaxed",
    "fit", "style", "women's", "womens", "women", "men's", "mens", "men",
}


def _significant_words(text: str | None) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-z']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _word_overlap_similarity(a: str | None, b: str | None) -> float:
    """Jaccard similarity over significant words -- much more meaningful
    for short product-name comparisons than raw character-level string
    similarity, which gives misleadingly non-trivial scores for two
    completely unrelated phrases just from incidental shared letters."""
    words_a, words_b = _significant_words(a), _significant_words(b)
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def _text_similarity(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    # Blend word-overlap (the primary, more meaningful signal) with a
    # small character-level component (catches near-duplicate phrasing
    # that word-overlap alone would miss, e.g. "blouse" vs "blouses").
    return 0.8 * _word_overlap_similarity(a, b) + 0.2 * SequenceMatcher(None, a.lower(), b.lower()).ratio()


def score_catalogue_match(trend: TrendProduct, product: Product) -> float:
    name_sim = _text_similarity(trend.ai_name, product.product_name)
    category_bonus = 0.15 if (
        trend.ai_category and product.category and trend.ai_category.lower() in product.category.lower()
    ) else 0.0
    color_bonus = 0.1 if (
        trend.ai_color and product.colors and trend.ai_color.lower() in (product.colors or "").lower()
    ) else 0.0
    score = min(1.0, name_sim + category_bonus + color_bonus)
    return round(score, 3)


def find_catalogue_matches(db: Session, trend_product: TrendProduct, max_results: int = 6) -> list[tuple[Product, float]]:
    """Ranked catalogue candidates for one trend product, highest score
    first, filtered to MIN_MATCH_SCORE. Scores every scraped COMPETITOR
    product currently in the database (excludes source='suburbia' --
    that's the buyer's own brand, not something to suggest back to
    itself as a "similar product"). Fine at the scale this project
    operates at (a few hundred products); if that grows into the
    thousands, add a cheap category pre-filter before scoring rather
    than changing the scoring itself."""
    candidates = (
        db.query(Product)
        .filter(Product.product_name.isnot(None))
        .filter(Product.source != "suburbia")
        .all()
    )
    scored = [(p, score_catalogue_match(trend_product, p)) for p in candidates]
    scored = [(p, s) for p, s in scored if s >= MIN_MATCH_SCORE]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:max_results]