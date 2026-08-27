"""
Deterministic, keyword-based "mock" AI provider.

This exists so the whole pipeline (scrape -> attributes -> analytics ->
gap analysis -> opportunities -> catalogue) runs and produces real,
inspectable output with ZERO external dependencies or API keys --
useful for local development, demos, and to validate the plumbing before
spending money/tokens on a real LLM. It is intentionally simple keyword
matching, NOT a substitute for real AI attribute extraction quality --
switch AI_PROVIDER=anthropic (see anthropic_provider.py) for production
use with real images/descriptions.

Per spec section 9, any attribute this can't confidently infer from the
product name/description text is left as "unknown" rather than guessed.
"""
from __future__ import annotations

import re
from typing import Optional

from app.services.ai.base import AIProvider, UNKNOWN

# Keyword -> value lookup tables. Order matters within each table (first
# match wins) so more specific terms can be listed before generic ones.
NECKLINE_KEYWORDS = {
    "v-neck": ["v-neck", "cuello v", "escote v"],
    "crew": ["crew neck", "cuello redondo", "cuello tortuga alto"],
    "turtleneck": ["turtleneck", "cuello tortuga", "cuello alto"],
    "polo": ["polo"],
    "boat": ["boat neck", "cuello barco"],
    "square": ["square neck", "cuello cuadrado"],
    "off_shoulder": ["off-shoulder", "off shoulder", "hombros descubiertos"],
}
SLEEVE_KEYWORDS = {
    "sleeveless": ["sleeveless", "sin mangas", "tirante"],
    "short": ["short sleeve", "manga corta"],
    "3/4": ["3/4", "manga 3/4", "manga al codo"],
    "long": ["long sleeve", "manga larga"],
    "batwing": ["batwing"],
}
FIT_KEYWORDS = {
    "oversized": ["oversized", "oversize", "holgado", "amplio"],
    "relaxed": ["relaxed", "relajado"],
    "slim": ["slim", "entallado", "ajustado"],
    "regular": ["regular", "estandar", "estándar"],
    "cropped": ["cropped", "corto"],
}
PATTERN_KEYWORDS = {
    "stripe": ["stripe", "striped", "rayas", "rayado"],
    "floral": ["floral", "flores"],
    "polka_dot": ["polka dot", "lunares"],
    "cable_knit": ["cable knit", "trenzado", "cable"],
    "graphic": ["graphic", "estampado grafico", "print"],
    "check": ["check", "cuadros", "plaid"],
    "solid": [],  # fallback default, checked last
}
COLOR_KEYWORDS = {
    "black": ["black", "negro"],
    "white": ["white", "blanco"],
    "cream": ["cream", "crema", "hueso"],
    "burgundy": ["burgundy", "burdeos", "vino"],
    "navy": ["navy", "marino"],
    "brown": ["brown", "cafe", "café", "chocolate"],
    "grey": ["grey", "gray", "gris"],
    "beige": ["beige"],
    "green": ["green", "verde"],
    "red": ["red", "rojo"],
    "pink": ["pink", "rosa"],
    "blue": ["blue", "azul"],
}
FABRIC_KEYWORDS = {
    "knit": ["knit", "punto", "tejido"],
    "cotton": ["cotton", "algodon", "algodón"],
    "wool": ["wool", "lana"],
    "silk": ["silk", "seda"],
    "satin": ["satin", "raso"],
    "chiffon": ["chiffon", "gasa"],
    "linen": ["linen", "lino"],
    "polyester": ["polyester", "poliester", "poliéster"],
}
STYLE_KEYWORDS = {
    "preppy": ["preppy", "polo"],
    "casual": ["casual"],
    "formal": ["formal", "oficina", "elegante"],
    "boho": ["boho", "bohemio"],
    "sporty": ["sporty", "deportivo"],
}


def _find_first(text: str, table: dict) -> Optional[str]:
    for value, keywords in table.items():
        for kw in keywords:
            if kw and re.search(re.escape(kw), text):
                return value
    return None


class MockAIProvider(AIProvider):
    name = "mock"

    def extract_attributes(
        self,
        product_name: str,
        description: Optional[str],
        category: str,
        image_path: Optional[str] = None,
    ) -> dict:
        text = f"{product_name or ''} {description or ''}".lower()

        result = self.empty_result(confidence=0.0)
        matched = 0
        total = 0

        for field, table in [
            ("neckline", NECKLINE_KEYWORDS),
            ("sleeve_type", SLEEVE_KEYWORDS),
            ("fit", FIT_KEYWORDS),
            ("pattern", PATTERN_KEYWORDS),
            ("primary_color", COLOR_KEYWORDS),
            ("fabric_type", FABRIC_KEYWORDS),
            ("style", STYLE_KEYWORDS),
        ]:
            total += 1
            value = _find_first(text, table)
            if value:
                result[field] = value
                matched += 1
            elif field == "pattern":
                # "solid" is a legitimate positive finding (absence of a
                # pattern keyword plus a garment description at all), not
                # an unknown -- but only if we have some text to go on.
                if text.strip():
                    result[field] = "solid"
                    matched += 1

        # silhouette / secondary_color / texture / details / length /
        # season are left "unknown" by this mock provider -- these need
        # either richer text or real vision analysis (see
        # anthropic_provider.py) to infer reliably; guessing them from
        # keywords alone would violate the "no hallucination" rule.

        result["confidence"] = round(matched / total, 2) if total else 0.0
        return result
