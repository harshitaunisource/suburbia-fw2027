"""
Pure structural currency detection -- NO AI/LLM involved anywhere in this
file. Replaces the old behavior of trusting a manually-typed dropdown
value for every product from a source, regardless of what the page
itself actually says.

Detection order (first confident match wins):
  1. Explicit machine-readable signals on the page itself:
     JSON-LD `priceCurrency`, Open Graph / product:price:currency meta,
     itemprop="priceCurrency" microdata.
  2. A 3-letter ISO 4217 code appearing in the price text itself
     (e.g. "MXN $499.00", "499.00 USD").
  3. A currency SYMBOL near the price text (mapped to the most likely
     ISO code -- symbols like "$" are inherently ambiguous across
     countries, so ties are broken using the page's own locale/domain
     signals, never guessed at random).
  4. The page's own <html lang="..."> / domain TLD, as a tie-breaker
     for ambiguous symbols only (e.g. "$" on a .mx domain -> MXN,
     the same "$" on a .com domain with no other signal -> USD).
  5. The explicitly configured fallback (the old dropdown value) --
     kept as the LAST resort, not the primary source, per the project
     requirement that currency must come from the page, not a guess
     typed once into a form.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

# Symbols that map unambiguously to exactly one ISO code.
UNAMBIGUOUS_SYMBOLS = {
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
    "₩": "KRW",
    "₺": "TRY",
    "₽": "RUB",
    "R$": "BRL",
    "Bs.": "BOB",
    "Bs": "BOB",
    "S/.": "PEN",
    "S/": "PEN",
    "zł": "PLN",
    "kr": "SEK",  # also DKK/NOK; refined by TLD below when possible
    "฿": "THB",
}

# "$" alone is used by ~20 countries. Map the country's TLD to the
# right code, and fall back to USD only when nothing else narrows it
# down (USD is the single most common meaning of a bare "$" globally).
DOLLAR_TLD_MAP = {
    "mx": "MXN",
    "us": "USD",
    "ca": "CAD",
    "au": "AUD",
    "nz": "NZD",
    "sg": "SGD",
    "hk": "HKD",
    "co": "COP",  # Colombia
    "cl": "CLP",
    "ar": "ARS",
    "uy": "UYU",
}

KR_TLD_MAP = {"se": "SEK", "no": "NOK", "dk": "DKK"}

# Explicit 3-letter ISO codes we accept if found verbatim in text near
# a price (case-insensitive). Deliberately a fixed allowlist rather
# than "any 3 uppercase letters" -- that would false-positive on
# unrelated acronyms (e.g. "NEW", "SALE" style badges).
KNOWN_ISO_CODES = {
    "USD", "MXN", "EUR", "GBP", "BRL", "INR", "CAD", "AUD", "NZD",
    "COP", "CLP", "ARS", "UYU", "PEN", "BOB", "SEK", "NOK", "DKK",
    "PLN", "TRY", "RUB", "KRW", "JPY", "CNY", "THB", "SGD", "HKD",
    "CHF", "ZAR", "PHP", "VND", "IDR", "MYR",
}

ISO_CODE_RE = re.compile(r"\b([A-Z]{3})\b")


def _tld_of(url: str) -> Optional[str]:
    host = urlparse(url).netloc.lower()
    parts = host.split(".")
    return parts[-1] if parts else None


def from_jsonld_or_meta(explicit_currency: Optional[str]) -> Optional[str]:
    """Validates a currency value already pulled from a structured
    source (JSON-LD `priceCurrency`, Open Graph `product:price:currency`,
    or microdata `itemprop=priceCurrency`) -- these are the single most
    reliable signal when present, since the site itself declared them
    for exactly this purpose. Returns None (never guesses) if the value
    doesn't look like a real ISO code."""
    if not explicit_currency:
        return None
    code = explicit_currency.strip().upper()
    return code if re.fullmatch(r"[A-Z]{3}", code) else None


def detect_currency(
    price_text: str,
    url: str,
    html_lang: Optional[str] = None,
    fallback: str = "USD",
) -> str:
    """Best-effort, purely structural currency detection from the raw
    text surrounding a scraped price. Never calls an AI model -- this
    is symbol/code/locale pattern matching only.
    """
    if not price_text:
        price_text = ""

    # 1. Explicit ISO code sitting right in the price text
    #    (e.g. "MXN $499.00", "499.00 USD").
    for match in ISO_CODE_RE.findall(price_text.upper()):
        if match in KNOWN_ISO_CODES:
            return match

    # 2. Unambiguous multi-char symbols first (longest match wins so
    #    "R$" isn't mis-caught by a later bare "$" check).
    for symbol, code in sorted(UNAMBIGUOUS_SYMBOLS.items(), key=lambda kv: -len(kv[0])):
        if symbol in price_text:
            if symbol == "kr":
                tld = _tld_of(url)
                return KR_TLD_MAP.get(tld, code)
            return code

    # 3. Bare "$" -- ambiguous, resolve via domain TLD first, then
    #    html lang, then the explicit fallback.
    if "$" in price_text or "US$" in price_text or "MX$" in price_text:
        if "MX$" in price_text:
            return "MXN"
        if "US$" in price_text:
            return "USD"
        tld = _tld_of(url)
        if tld in DOLLAR_TLD_MAP:
            return DOLLAR_TLD_MAP[tld]
        if html_lang:
            lang = html_lang.lower()
            if lang.startswith("es-mx"):
                return "MXN"
            if lang.startswith("en-us") or lang == "en":
                return "USD"
            if lang.startswith("en-gb"):
                return "GBP"
            if lang.startswith("en-au"):
                return "AUD"
            if lang.startswith("en-ca") or lang.startswith("fr-ca"):
                return "CAD"
        return "USD"

    if "¥" in price_text:
        tld = _tld_of(url)
        return "JPY" if tld == "jp" else "CNY"

    # 4. Nothing on the page told us -- last resort, the configured
    #    fallback (what used to be the ONLY source of truth).
    return fallback