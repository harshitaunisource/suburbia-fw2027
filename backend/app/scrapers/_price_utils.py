"""
Shared price-extraction helpers.

These exist because the exact same three bugs showed up independently in
Zara, ASOS and H&M during live testing:
  1. IndexError when a page has *no* matching price text at all
     (prices[0] on an empty list).
  2. A fixed "first N characters of the page" window missing the price
     entirely on pages with a lot of nav/header text before the real
     product info (confirmed live on ASOS).
  3. TypeError from comparing `original_price > price` when one of the
     two is None.

Centralizing the fix here means every current and future scraper gets it
for free instead of relying on each site module re-implementing it
correctly by hand.
"""
from __future__ import annotations

import re
from typing import Optional

PRICE_RE = re.compile(r"\$?\s?([\d][\d,]*\.\d{2})")


def extract_prices_near(text: str, anchor: Optional[str], window: int = 1500) -> list[float]:
    """Finds $-amounts in `text`, preferring a window around `anchor`
    (e.g. the product name, or a label like 'Precio') if it's found, and
    falling back to a full-text scan otherwise. Never raises -- returns
    an empty list if nothing matches."""
    scoped = text
    if anchor:
        idx = text.find(anchor)
        if idx != -1:
            scoped = text[idx: idx + window]

    prices = [float(p.replace(",", "")) for p in PRICE_RE.findall(scoped)]
    if not prices and scoped is not text:
        # Anchor window missed -- fall back to scanning the whole page
        # rather than silently returning nothing.
        prices = [float(p.replace(",", "")) for p in PRICE_RE.findall(text)]
    return prices


def current_and_original(prices: list[float]) -> tuple[Optional[float], Optional[float]]:
    """Given a list of found price numbers (in the order they appeared on
    the page), returns (current_price, original_price_if_discounted).
    Handles 0, 1, and 2+ matches safely -- this is the exact shape of bug
    that crashed the Zara scraper live (IndexError on an empty list)."""
    if not prices:
        return None, None
    if len(prices) == 1:
        return prices[0], None
    # Convention used across this project: when two distinct prices are
    # present, the larger one is the original/list price and the smaller
    # is the current/sale price -- true regardless of which one appears
    # first in the page's DOM order.
    lo, hi = min(prices), max(prices)
    if lo == hi:
        return lo, None
    return lo, hi


def discount_percentage(price: Optional[float], original_price: Optional[float]) -> Optional[float]:
    """Safe discount % calculation -- never raises on None inputs, which
    is the exact TypeError that crashed Zara live (`original_price > price`
    when price was None)."""
    if not price or not original_price or original_price <= price:
        return None
    return round((1 - price / original_price) * 100, 1)
