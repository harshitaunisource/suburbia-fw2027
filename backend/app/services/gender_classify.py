"""
Gender classification for classic-scraper Product rows.

BACKGROUND: Gender.GIRLS/BOYS/etc. already existed as a real, explicit
field on Product (see models.py's Gender enum), but it was only ever
populated for the "generic" scraping path (Search Products / Explore
Categories / Add Brand), which is told the gender up front because the
person configuring that source picks it. The classic per-brand scrapers
(suburbia, zara, hm, c_and_a, primark, old_navy, shein, boohoo, asos,
textilon) -- the ones that feed the main Products page -- never set
gender at all, so every row from that pipeline has gender=NULL.

This is exactly why Primark's girls' blouses showed up indistinguishable
from ladies' blouses: the scraper's link-discovery grabbed every product
detail page link it found on/around the category page (including
cross-sell/recommendation modules for other product lines), and nothing
downstream ever separated them back out.

This module infers gender from the product's own name text -- the only
signal available for rows that were never told their gender up front.
Order matters: more specific patterns (girls/boys) are checked before
the more generic "kids" pattern, and explicit men's/women's signals are
checked before falling back to a default. The classic scrapers on this
project are configured for women's sweaters/blouses/pajamas, so
`default_gender=Gender.WOMENS` reflects that most rows genuinely are
women's items even when the name has no gender word in it at all (e.g.
"ASOS DESIGN v-neck relaxed sweater in green") -- the classifier's job
is to catch the minority of rows that explicitly say otherwise, not to
second-guess the ones that don't.
"""
import re

from app.models import Gender

_GIRLS_RE = re.compile(r"\b(girls?|girl's|toddler girls?)\b", re.IGNORECASE)
_BOYS_RE = re.compile(r"\b(boys?|boy's|toddler boys?)\b", re.IGNORECASE)
_KIDS_RE = re.compile(r"\b(kids?|children'?s?|junior|youth|toddlers?|babies|baby)\b", re.IGNORECASE)
_MENS_RE = re.compile(r"\b(men'?s|mens|gentlemen)\b", re.IGNORECASE)
_WOMENS_RE = re.compile(r"\b(women'?s|womens|ladies|lady'?s)\b", re.IGNORECASE)


def classify_gender(product_name: str | None, category: str | None = None, subcategory: str | None = None, default_gender: Gender = Gender.WOMENS) -> Gender:
    # `subcategory` is the most reliable signal when a scraper already
    # knows it -- e.g. Textilon scrapes separate men's and women's URLs
    # and stamps subcategory="men"/"women" accordingly (see textilon.py),
    # the same kind of known-up-front signal GenericSourceConfig.gender
    # uses elsewhere. Trust it over guessing from the name whenever it's
    # actually present.
    if subcategory:
        sub = subcategory.strip().lower()
        if sub in ("men", "man", "mens", "male"):
            return Gender.MENS
        if sub in ("women", "woman", "womens", "female"):
            return Gender.WOMENS
        if sub in ("boys", "boy"):
            return Gender.BOYS
        if sub in ("girls", "girl"):
            return Gender.GIRLS
        if sub in ("kids", "children", "child"):
            return Gender.KIDS

    text = product_name or ""
    if _GIRLS_RE.search(text):
        return Gender.GIRLS
    if _BOYS_RE.search(text):
        return Gender.BOYS
    if _MENS_RE.search(text):
        return Gender.MENS
    if _WOMENS_RE.search(text):
        return Gender.WOMENS
    if _KIDS_RE.search(text):
        return Gender.KIDS
    return default_gender