"""
Factory that picks the active AI provider from the AI_PROVIDER env var.

  AI_PROVIDER=mock       (default) -- zero dependencies, keyword-based,
                          good for local dev / demoing the full pipeline.
  AI_PROVIDER=anthropic  -- real LLM extraction via Claude. Requires
                          ANTHROPIC_API_KEY and `pip install anthropic`.
  AI_PROVIDER=openai     -- real LLM extraction via OpenAI. Requires
                          OPENAI_API_KEY and `pip install openai`.
"""
import os

from app.services.ai.base import AIProvider


def get_ai_provider() -> AIProvider:
    provider = os.getenv("AI_PROVIDER", "mock").lower()
    if provider == "anthropic":
        from app.services.ai.anthropic_provider import AnthropicAIProvider
        return AnthropicAIProvider()
    if provider == "openai":
        from app.services.ai.openai_provider import OpenAIProvider
        return OpenAIProvider()
    if provider == "mock":
        from app.services.ai.mock_provider import MockAIProvider
        return MockAIProvider()
    raise ValueError(f"Unknown AI_PROVIDER='{provider}'. Use 'mock', 'anthropic', or 'openai'.")