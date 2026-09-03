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

# European/Latin American decimal format: comma as the decimal
# separator, period as an optional thousands separator (e.g. "29,99 €",
# "1.234,56"). CONFIRMED live necessary: Women'Secret's real prices
# render as "29,99 €" / "14,99 €" (real debug HTML, 2026-09-01), which
# PRICE_RE above never matches at all (it requires a literal period
# before exactly 2 decimal digits) -- every Women'Secret price was
# silently coming back as None. Kept as a SEPARATE fallback pattern
# (only tried if PRICE_RE finds nothing) rather than replacing PRICE_RE,
# so every already-working scraper (Suburbia, ASOS, Zara, C&A, etc.,
# all of which use period-decimal formats) is completely unaffected.
EURO_PRICE_RE = re.compile(r"([\d]{1,3}(?:\.\d{3})*,\d{2})(?:\s?€|\s?Bs\.?|\s?R\$)?")


def extract_prices_near(text: str, anchor: Optional[str], window: int = 1500) -> list[float]:
    """Finds $-amounts in `text`, preferring a window around `anchor`
    (e.g. the product name, or a label like 'Precio') if it's found, and
    falling back to a full-text scan otherwise. Never raises -- returns
    an empty list if nothing matches.

    Tries US/MX-style period-decimal amounts first (the format every
    already-working scraper in this project uses), then falls back to
    European/Latin American comma-decimal amounts (e.g. "29,99 €") only
    if the first pattern found nothing -- confirmed necessary for
    Women'Secret, whose real prices never matched the period-decimal
    pattern at all."""
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

    if not prices:
        # Comma-decimal fallback (European/Latin American format) --
        # strip thousands-separator periods, then swap the decimal comma
        # for a period so float() parses it correctly.
        prices = [float(p.replace(".", "").replace(",", ".")) for p in EURO_PRICE_RE.findall(scoped)]
        if not prices and scoped is not text:
            prices = [float(p.replace(".", "").replace(",", ".")) for p in EURO_PRICE_RE.findall(text)]

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
    lo, hi = min(prices), max(prices)
    if lo == hi:
        return lo, None
    return lo, hi


def discount_percentage(price: Optional[float], original_price: Optional[float]) -> Optional[float]:
    """Safe discount % calculation -- never raises on None inputs."""
    if not price or not original_price or original_price <= price:
        return None
    return round((1 - price / original_price) * 100, 1)