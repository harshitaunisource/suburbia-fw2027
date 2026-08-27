"""
AI provider abstraction layer (spec section 4/9: "Create an abstraction
layer so the AI provider can be changed later... Do not hard-code the
entire system around one AI provider.").

Every provider implements `extract_attributes`, taking whatever text/
image info is available for a product and returning a plain dict of
attribute -> value using ONLY the vocabulary in ATTRIBUTE_FIELDS. Any
attribute the provider isn't confident about must come back as the
string "unknown" -- never guessed/hallucinated (spec section 9).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

# Attributes tracked for both garment types (see spec section 9). Blouses
# don't have "knit appearance"; sweaters don't have "fabric appearance" --
# both are folded into `texture`/`fabric_type` here to keep one shared
# schema per the product_attributes table in models.py.
ATTRIBUTE_FIELDS = [
    "fit",
    "silhouette",
    "neckline",
    "sleeve_type",
    "length",
    "pattern",
    "primary_color",
    "secondary_color",
    "fabric_type",
    "texture",
    "style",
    "details",
    "season",
]

UNKNOWN = "unknown"


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    def extract_attributes(
        self,
        product_name: str,
        description: Optional[str],
        category: str,
        image_path: Optional[str] = None,
    ) -> dict:
        """Returns a dict with keys from ATTRIBUTE_FIELDS (value or
        "unknown" for each) plus a numeric "confidence" in [0, 1]."""
        raise NotImplementedError

    @staticmethod
    def empty_result(confidence: float = 0.0) -> dict:
        result = {field: UNKNOWN for field in ATTRIBUTE_FIELDS}
        result["confidence"] = confidence
        return result
