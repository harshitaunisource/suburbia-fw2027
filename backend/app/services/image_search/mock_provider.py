from __future__ import annotations

from app.services.image_search.base import ImageSearchHit, ImageSearchProvider


class MockImageSearchProvider(ImageSearchProvider):
    """Zero-cost, deterministic placeholder results so the rest of the
    matching pipeline can be built/tested without a Tavily key or
    spending real quota on every test run."""
    name = "mock"

    def search(self, query: str, max_results: int = 6) -> list[ImageSearchHit]:
        return [
            ImageSearchHit(
                image_url=f"https://picsum.photos/seed/{abs(hash(query)) % 10000}-{i}/400/500",
                title=f"{query} (mock result {i + 1})",
                source_url="https://example.com/mock-result",
            )
            for i in range(min(max_results, 6))
        ]