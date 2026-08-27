"""
Base scraper interface. Every site gets its own module implementing this,
so one site breaking (structure change / anti-bot block) never affects the
others. See suburbia.py for a full working reference implementation.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", Path(__file__).resolve().parents[2] / "storage"))

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}


@dataclass
class ScrapedProduct:
    """Normalized record every scraper must return. Kept flat and simple
    on purpose -- this maps almost 1:1 onto the `products` table."""
    source: str
    brand: Optional[str]
    category: str
    subcategory: Optional[str]
    product_name: str
    product_code: Optional[str]
    product_url: str
    image_url: Optional[str]
    additional_image_urls: list[str] = field(default_factory=list)
    price: Optional[float] = None
    currency: str = "MXN"
    original_price: Optional[float] = None
    discount_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    description: Optional[str] = None
    material: Optional[str] = None
    sizes: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    availability: Optional[str] = None


class ScraperError(Exception):
    """Raised when a source cannot currently be scraped reliably.
    Scrapers must raise this instead of returning fabricated data.

    IMPORTANT: this is the ONE canonical ScraperError class for the whole
    project. playwright_base.py imports and re-raises this exact class
    (it does NOT define its own) -- app/services/ingest.py's
    `except ScraperError` needs to catch failures from every scraper,
    httpx-based or Playwright-based, or a failure gets treated as an
    unhandled crash: the scraper's resources (browser process, for
    Playwright-based scrapers) never get released via .close(), which
    then breaks the NEXT scraper run in the same process with a
    confusing, unrelated-looking "Sync API inside the asyncio loop"
    error. If you ever add a new scraper base class, import ScraperError
    from here -- never define a second one."""


def save_image_bytes(
    content: bytes,
    source_name: str,
    category: str,
    product_code: Optional[str],
    image_url: str,
    suffix: str = "",
) -> str:
    """Shared image-saving logic used by both BaseScraper.download_image
    (httpx-based scrapers) and PlaywrightScraper.download_image
    (Playwright-based scrapers) -- kept in one place so a fix here (path
    handling, filename collisions, etc.) never needs to be made twice."""
    ext = os.path.splitext(image_url.split("?")[0])[1] or ".jpg"
    safe_code = product_code or hashlib.md5(image_url.encode()).hexdigest()[:12]
    filename = f"{safe_code}{suffix}{ext}"

    target_dir = STORAGE_ROOT / "products" / source_name / category
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    with open(target_path, "wb") as f:
        f.write(content)

    return str(target_path.relative_to(STORAGE_ROOT.parent).as_posix())


class BaseScraper:
    source_name: str = "base"

    def __init__(self, timeout: float = 20.0, connect_retries: int = 3):
        # Retries at the transport level cover exactly the failure mode
        # we hit in practice: transient DNS resolution / TCP connect
        # errors (e.g. "getaddrinfo failed") that succeed on a plain
        # retry a moment later. httpx does NOT retry on 4xx/5xx response
        # codes or after a response was already received -- only on
        # failures to establish the connection itself -- which is the
        # right scope here: we still want a real 403 to surface as a
        # ScraperError rather than being silently retried forever.
        transport = httpx.HTTPTransport(retries=connect_retries)
        self.client = httpx.Client(
            headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True, transport=transport
        )
        # Prints the actual reason for the first few image-download
        # failures per scraper run, instead of silently swallowing every
        # single one into an undifferentiated "failed" count -- this is
        # exactly the visibility gap that made a 100%-failed ASOS image
        # batch (65/65, then 58/58) undiagnosable from the logs alone.
        self._image_debug_remaining = 5

    # -- to implement per-site --------------------------------------------
    def scrape_category(self, url: str, max_pages: int | None = None) -> list[ScrapedProduct]:
        raise NotImplementedError

    def scrape_product(self, url: str) -> ScrapedProduct:
        raise NotImplementedError

    # -- shared helpers ------------------------------------------------------
    def download_image(self, image_url: str, category: str, product_code: str, suffix: str = "") -> Optional[str]:
        """Downloads an image to storage/products/<source>/<category>/ and
        returns the local relative path, or None on failure (never raises --
        a failed image download shouldn't kill the whole scrape)."""
        if not image_url:
            return None
        try:
            resp = self.client.get(image_url)
            resp.raise_for_status()
        except Exception as e:
            # Broad catch (not just httpx.HTTPError) is intentional: a
            # malformed image_url (e.g. a protocol-relative "//host/..."
            # URL missing "https:") raises httpx.InvalidURL, which is NOT
            # a subclass of httpx.HTTPError -- a narrower catch here would
            # let that specific failure mode through with zero diagnostic
            # output, silently miscounting it as just another "failed".
            if self._image_debug_remaining > 0:
                self._image_debug_remaining -= 1
                status = getattr(getattr(e, "response", None), "status_code", "n/a")
                print(f"[{self.source_name}] image download failed (status={status}): "
                      f"{image_url} -- {type(e).__name__}: {e}", flush=True)
            return None

        return save_image_bytes(resp.content, self.source_name, category, product_code, image_url, suffix)

    def close(self):
        self.client.close()