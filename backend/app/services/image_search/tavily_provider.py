"""
Real web image search via tavily.com's official Python SDK. Free tier:
1,000 search credits/month, no credit card required to sign up
(confirmed as of 2026 -- verify current terms at tavily.com before
relying on this for production volume, since API terms can change).

Setup:
  1. Sign up at https://tavily.com (no card needed for the free tier).
  2. Copy your API key (starts with "tvly-") from the dashboard.
  3. Set TAVILY_API_KEY in .env, and IMAGE_SEARCH_PROVIDER=tavily.

include_images=True costs more credits per call than a plain text
search (5 credits vs 1, per Tavily's pricing) -- at 1,000 free
credits/month that's ~200 trend-product searches/month before the free
tier runs out, which is a real, worth-knowing limit for a merchant
running this against every product in a large trend deck.
"""
from __future__ import annotations

from app.services.image_search.base import ImageSearchError, ImageSearchHit, ImageSearchProvider


class TavilyImageSearchProvider(ImageSearchProvider):
    name = "tavily"

    def __init__(self, api_key: str):
        if not api_key:
            raise ImageSearchError(
                "Web image search is set to Tavily but TAVILY_API_KEY isn't set. "
                "Add it to .env, or set IMAGE_SEARCH_PROVIDER=mock to keep testing without a key."
            )
        try:
            from tavily import TavilyClient
        except ImportError as e:
            raise ImageSearchError(
                "The 'tavily-python' package is not installed. Run: pip install tavily-python"
            ) from e
        self._client = TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 6) -> list[ImageSearchHit]:
        try:
            response = self._client.search(
                query,
                search_depth="basic",
                max_results=max_results,
                include_images=True,
            )
        except Exception as e:
            raise ImageSearchError(f"Tavily search failed for query '{query}': {e}") from e

        hits: list[ImageSearchHit] = []

        # Prefer per-result images (carries a title/source page to show
        # the merchant real context for each image) when the API/SDK
        # version returns them; fall back to the flat top-level `images`
        # list (just URLs, no per-image context) otherwise -- both shapes
        # are seen across Tavily API versions.
        for result in response.get("results", []) or []:
            for img in result.get("images", []) or []:
                img_url = img if isinstance(img, str) else (img.get("url") if isinstance(img, dict) else None)
                if not img_url:
                    continue
                hits.append(ImageSearchHit(
                    image_url=img_url,
                    title=result.get("title") or query,
                    source_url=result.get("url") or "",
                ))
                if len(hits) >= max_results:
                    return hits

        if not hits:
            for img in response.get("images", []) or []:
                img_url = img if isinstance(img, str) else (img.get("url") if isinstance(img, dict) else None)
                if not img_url:
                    continue
                hits.append(ImageSearchHit(image_url=img_url, title=query, source_url=""))
                if len(hits) >= max_results:
                    break

        return hits