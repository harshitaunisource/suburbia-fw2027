"""
OpenAI-backed AI provider -- real LLM attribute extraction, same
contract as anthropic_provider.py (see that file's docstring: this
abstraction exists specifically so a new provider is a drop-in, nothing
else in the app needs to change).

Requires: pip install openai, and OPENAI_API_KEY set in the environment.

MODEL CHOICE: defaults to a small/cheap model, not a flagship one --
this is a short, structured JSON-extraction task (a handful of short
fields from a product name + description), not something that benefits
from a frontier model's extra reasoning. Override with OPENAI_MODEL if
you want a different one, but there is no quality reason to reach for
an expensive model here.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from app.services.ai.base import ATTRIBUTE_FIELDS, AIProvider

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

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


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self):
        try:
            import openai  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from e
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Set it in your environment (or a "
                ".env file) to use AI_PROVIDER=openai, or use AI_PROVIDER=mock "
                "instead."
            )
        import openai
        self._client = openai.OpenAI(api_key=api_key)

    def extract_attributes(
        self,
        product_name: str,
        description: Optional[str],
        category: str,
        image_path: Optional[str] = None,
    ) -> dict:
        user_text = f"Product name: {product_name}\nDescription: {description or '(none provided)'}"

        try:
            response = self._client.chat.completions.create(
                model=MODEL,
                max_tokens=500,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT.format(category=category)},
                    {"role": "user", "content": user_text},
                ],
            )
            raw_text = response.choices[0].message.content.strip()
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