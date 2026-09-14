"""
Classifies a single product image with no accompanying text -- this is
the actual situation a buyer trend deck or vendor catalogue puts you in:
"images here and there", no product names or descriptions attached.

Separate from app/services/ai/ (the existing AIProvider abstraction) on
purpose: that one extracts structured *attributes* from a product's
*name and description text* for the competitor-scraping pipeline, and
its OpenAI implementation never actually sends image bytes to the model
despite taking an image_path parameter. This module's whole job is
vision classification from the image alone, so it's a distinct,
smaller piece rather than overloading that contract.

Swappable the same way app/services/ai/factory.py is: set
VISION_PROVIDER=mock (default, no API key, deterministic placeholder
text -- good for building/testing the rest of the pipeline for free) or
VISION_PROVIDER=openai (real, needs OPENAI_API_KEY).
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class VisionClassification:
    name: str               # short, search-engine-friendly: "Blue striped women's blouse, loose fit"
    category: Optional[str]  # e.g. "blouses", "sweaters"
    color: Optional[str]
    pattern: Optional[str]
    description: Optional[str]
    confidence: float
    error: Optional[str] = None


def _mock_classify(image_bytes: bytes) -> VisionClassification:
    """Zero-cost, deterministic placeholder so the rest of the pipeline
    (extraction -> classify -> match -> select -> PPT) can be built and
    tested end-to-end without an OpenAI key or spending real money on
    every test run. Never used in production once VISION_PROVIDER=openai
    is set."""
    # Deterministic-but-varied off the image's own byte length, purely so
    # repeated test runs against the same fixture images produce stable,
    # distinguishable results instead of everything collapsing to one name.
    n = len(image_bytes) % 5
    names = [
        "Striped women's blouse, loose fit",
        "Cable knit crew neck sweater",
        "Floral print wrap dress",
        "Ribbed turtleneck sweater",
        "Button-up collared shirt",
    ]
    return VisionClassification(
        name=names[n],
        category="blouses" if n in (0, 4) else ("sweaters" if n in (1, 3) else "dresses"),
        color="unknown",
        pattern="unknown",
        description="(mock classification -- set VISION_PROVIDER=openai for real results)",
        confidence=0.3,
    )


_SYSTEM_PROMPT = """You are a fashion product identification system. You are shown ONE
product photo with no other context (no brand, no name, no description).

Respond with ONLY a JSON object, no other text, with exactly these keys:
- "name": a short, specific, search-engine-friendly product name a buyer
  would type into a search bar, e.g. "Blue striped women's blouse, loose
  fit" or "Cable knit crew neck cardigan, beige". Include garment type,
  color, pattern (if any), and fit/style if visible. This is the single
  most important field -- it's used both to search the web for similar
  products and to match against a vendor catalogue.
- "category": one short word/phrase for the garment category (e.g.
  "blouses", "sweaters", "dresses", "pajamas"). "unknown" if not
  determinable.
- "color": the dominant color. "unknown" if not determinable.
- "pattern": e.g. "striped", "floral", "solid", "plaid". "unknown" if
  none is visible or determinable.
- "description": one sentence of additional visual detail (silhouette,
  neckline, sleeve type, etc.) beyond what's in "name".
- "confidence": a number from 0 to 1 for how confident you are this is
  actually a clear, classifiable product photo (not a logo, a blank
  slide, decorative graphic, or too ambiguous to describe).

If the image is not a usable product photo at all, still return valid
JSON with "name" as a brief description of what the image actually shows
and "confidence" at or near 0.
"""


def _openai_classify(image_bytes: bytes, content_type: str) -> VisionClassification:
    import openai

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return VisionClassification(
            name="(no OPENAI_API_KEY set)", category=None, color=None, pattern=None,
            description=None, confidence=0.0,
            error="OPENAI_API_KEY is not set -- set it in .env, or set VISION_PROVIDER=mock to keep testing without a key.",
        )

    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{content_type};base64,{b64}"

    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=400,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Identify this product."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
    except Exception as e:
        # Never crash a batch classification run on one bad image/API call.
        return VisionClassification(
            name="(classification failed)", category=None, color=None, pattern=None,
            description=None, confidence=0.0, error=str(e),
        )

    def _clean(v):
        v = (v or "").strip()
        return None if not v or v.lower() == "unknown" else v

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return VisionClassification(
        name=(data.get("name") or "Unidentified product").strip(),
        category=_clean(data.get("category")),
        color=_clean(data.get("color")),
        pattern=_clean(data.get("pattern")),
        description=_clean(data.get("description")),
        confidence=confidence,
    )


def classify_product_image(image_bytes: bytes, content_type: str = "image/png") -> VisionClassification:
    provider = os.getenv("VISION_PROVIDER", "mock").lower()
    if provider == "openai":
        return _openai_classify(image_bytes, content_type)
    if provider == "mock":
        return _mock_classify(image_bytes)
    raise ValueError(f"Unknown VISION_PROVIDER='{provider}'. Use 'mock' or 'openai'.")