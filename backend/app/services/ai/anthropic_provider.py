"""
Anthropic-backed AI provider -- real LLM attribute extraction.

Requires: pip install anthropic, and ANTHROPIC_API_KEY set in the
environment. Falls back to raising a clear error (never silently to
fabricated data) if the key is missing or the call fails -- the caller
(app/services/attributes.py) treats that as "unknown, low confidence"
for that product rather than crashing the whole batch.

This is intentionally a thin, swappable layer: if you later want OpenAI,
Gemini, a local model, etc., implement AIProvider the same way and wire
it up in factory.py -- nothing else in the app needs to change (spec
section 4: "Create an abstraction layer so the AI provider can be
changed later").
"""
from __future__ import annotations

import json
import os
from typing import Optional

from app.services.ai.base import ATTRIBUTE_FIELDS, AIProvider

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

SYSTEM_PROMPT = f"""You are a fashion product attribute extraction system.
Given a product name and description for a women's {{category}}, extract
these attributes: {", ".join(ATTRIBUTE_FIELDS)}.

Rules:
- Respond with ONLY a JSON object, no other text.
- Keys must be exactly: {", ".join(ATTRIBUTE_FIELDS)}, plus "confidence".
- If you cannot confidently determine an attribute from the given text,
  its value MUST be the string "unknown". Do not guess or hallucinate.
- "confidence" is a number from 0 to 1 representing your overall
  confidence across the attributes you *did* fill in.
"""


class AnthropicAIProvider(AIProvider):
    name = "anthropic"

    def __init__(self):
        try:
            import anthropic  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "The 'anthropic' package is not installed. Run: "
                "pip install anthropic"
            ) from e
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Set it in your environment "
                "(or a .env file) to use AI_PROVIDER=anthropic, or use "
                "AI_PROVIDER=mock instead."
            )
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def extract_attributes(
        self,
        product_name: str,
        description: Optional[str],
        category: str,
        image_path: Optional[str] = None,
    ) -> dict:
        user_text = f"Product name: {product_name}\nDescription: {description or '(none provided)'}"

        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=500,
                system=SYSTEM_PROMPT.format(category=category),
                messages=[{"role": "user", "content": user_text}],
            )
            raw_text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            raw_text = raw_text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.strip("`")
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            data = json.loads(raw_text)
        except Exception as e:
            # Never crash the batch on one bad AI call / bad JSON -- fall
            # back to an all-unknown, zero-confidence result and let the
            # caller log it.
            result = self.empty_result(confidence=0.0)
            result["_error"] = str(e)
            return result

        result = self.empty_result(confidence=0.0)
        for field in ATTRIBUTE_FIELDS:
            result[field] = data.get(field, "unknown") or "unknown"
        try:
            result["confidence"] = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            result["confidence"] = 0.0
        return result
