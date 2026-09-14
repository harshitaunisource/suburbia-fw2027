import os

from app.services.image_search.base import ImageSearchProvider


def get_image_search_provider() -> ImageSearchProvider:
    provider = os.getenv("IMAGE_SEARCH_PROVIDER", "mock").lower()
    if provider == "tavily":
        from app.services.image_search.tavily_provider import TavilyImageSearchProvider
        return TavilyImageSearchProvider(api_key=os.getenv("TAVILY_API_KEY", ""))
    if provider == "mock":
        from app.services.image_search.mock_provider import MockImageSearchProvider
        return MockImageSearchProvider()
    raise ValueError(f"Unknown IMAGE_SEARCH_PROVIDER='{provider}'. Use 'mock' or 'tavily'.")