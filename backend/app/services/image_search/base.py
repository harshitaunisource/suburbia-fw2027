"""
Swappable web image search provider -- the "go to the internet and find
similar products, just take the images" part of Trend Matching.

Deliberately NOT scraping a search engine's results page directly (e.g.
Google Images): that breaks ToS and gets blocked almost immediately,
the same class of fragility already seen with the competitor-site
scrapers elsewhere in this project. Uses a real search API instead.

  IMAGE_SEARCH_PROVIDER=mock    (default) -- zero cost, no key, returns
                                 placeholder image URLs. Good for
                                 building/testing the rest of the
                                 pipeline for free.
  IMAGE_SEARCH_PROVIDER=tavily  -- real results via tavily.com. Free
                                 tier: 1,000 credits/month, no credit
                                 card. Needs TAVILY_API_KEY.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ImageSearchError(Exception):
    pass


@dataclass
class ImageSearchHit:
    image_url: str
    title: str
    source_url: str  # the page the image was found on -- shown for context, never hidden from the merchant


class ImageSearchProvider(ABC):
    name: str = "base"

    @abstractmethod
    def search(self, query: str, max_results: int = 6) -> list[ImageSearchHit]:
        raise NotImplementedError