"""
Single source of truth for "what price do we actually use" across this
entire project. Created after repeated real bugs from different parts of
the codebase each re-deriving this logic slightly differently (or not at
all): Products.jsx displaying the discounted price as primary with MRP
struck through as an afterthought, the "from-product" catalogue endpoint
originally copying the discounted price, and GenericProduct not even
having a column to store the pre-discount price at all.

RULE (explicit, repeated instruction): NEVER use a discounted/sale price
for any business purpose in this project -- not display, not analytics,
not catalogue/PPT/export. Always use MRP (the pre-discount list price).
`original_price` is only populated when a product IS on sale (see each
scraper's discount-detection logic) -- when it's None/0, `price` already
IS the MRP, since there's no discount to begin with.

Every place in this codebase that needs "the price" -- Python or the API
response a frontend consumes -- should go through this function (or the
`mrp` field it powers on ProductOut/GenericProductOut), not re-implement
the price/original_price fallback logic itself.
"""
from __future__ import annotations

from typing import Optional


def compute_mrp(price: Optional[float], original_price: Optional[float]) -> Optional[float]:
    """Returns the MRP (pre-discount list price) -- original_price when
    the item is actually on sale, otherwise price itself (which already
    IS the MRP when there's no discount). Never returns a discounted
    price."""
    if original_price and original_price > 0:
        return original_price
    return price