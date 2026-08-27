"""
Base class for scrapers that need a real browser instead of plain httpx --
i.e. sites that are either full client-side-rendered SPAs (Zara), protected
by bot detection that fingerprints the TLS/browser handshake itself (H&M's
Akamai WAF), or that challenge automated traffic with a CAPTCHA/redirect
(SHEIN).

Use this instead of BaseScraper (base.py) when:
  - A plain httpx GET returns a near-empty app shell -- the site needs JS
    execution to render anything.
  - A plain httpx GET gets a 403 from a WAF even with full realistic
    headers -- the block is happening at the TLS fingerprint / behavioral
    level, which only a real browser client can pass.

Requires Playwright + a browser to be installed locally:
    pip install playwright
    python -m playwright install chromium
    python -m playwright install chrome   # optional, tried first if present

NOTE: this could not be executed or verified from the sandboxed build
environment used to write this project (no outbound network access there
at all, let alone a place to run a real browser). It must be smoke-tested
from a real machine before relying on it -- same as every scraper here.
"""
from __future__ import annotations

import os
from typing import Optional

from playwright.sync_api import sync_playwright

from app.scrapers.base import ScraperError, save_image_bytes

# Re-exported so existing `from app.scrapers.playwright_base import
# ScraperError` imports elsewhere keep working -- but this is now the
# SAME class as app.scrapers.base.ScraperError, not a second one. A
# previous version of this file defined its own separate ScraperError
# class here, which meant app/services/ingest.py's `except ScraperError`
# (importing from base.py) silently failed to catch failures from every
# Playwright-based scraper -- the scraper's browser process was then
# never closed, leaking into and crashing the NEXT scrape in the same
# process with an unrelated-looking "Sync API inside the asyncio loop"
# error. Always import ScraperError from app.scrapers.base -- never
# define a second one anywhere in this project.
__all__ = ["PlaywrightScraper", "ScraperError", "DEFAULT_USER_AGENT", "BLOCK_TEXT_MARKERS"]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Text markers used to detect a genuine bot-challenge/block page. Kept
# deliberately narrow and multi-word: a bare generic word like "captcha"
# or "unusual traffic" is too likely to appear as an incidental substring
# on a normal, unblocked page (e.g. a reCAPTCHA widget on an unrelated
# newsletter signup form, or a footer legal notice) -- that false-positive
# is exactly what caused a real, working ASOS page to be reported as
# blocked. Every phrase below is a distinctive, multi-word string that
# only appears on an actual interstitial/challenge page.
BLOCK_TEXT_MARKERS = [
    "verify you are human",
    "verificar que eres humano",
    "acceso denegado",
    "access denied",
    "robot check",
    "pardon our interruption",
    "request blocked",
    "are you a human",
    "complete the security check",
    "enable javascript and cookies to continue",
]


class PlaywrightScraper:
    source_name: str = "base"

    def __init__(self, headless: bool = True, locale: str = "es-MX", timeout_ms: int = 30000):
        self.timeout_ms = timeout_ms
        self._pw = sync_playwright().start()
        try:
            # Prefer real installed Chrome (harder to fingerprint as a bot)
            self.browser = self._pw.chromium.launch(headless=headless, channel="chrome")
        except Exception:
            # Falls back to Playwright's bundled Chromium, which is
            # guaranteed compatible with this Playwright version even if
            # a real Chrome channel isn't installed or crashes on launch
            # (confirmed failure mode live: real Chrome closing instantly
            # under some flag combinations).
            self.browser = self._pw.chromium.launch(headless=headless)
        self.context = self.browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale=locale,
            viewport={"width": 1366, "height": 900},
        )
        # NOTE: image downloads for Playwright-based scrapers now go
        # through self.context.request (Playwright's own APIRequestContext,
        # bound to the same browser context) instead of a separate plain
        # httpx client -- see download_image() below for why. The old
        # _image_debug_remaining counter still limits how many detailed
        # failure lines get printed per run.
        self._image_debug_remaining = 5

    def get_rendered_html(
        self,
        url: str,
        wait_selector: Optional[str] = None,
        wait_ms: int = 1500,
        scroll: bool = False,
        check_blocked: bool = True,
        referer: Optional[str] = None,
        debug_save_path: Optional[str] = None,
    ) -> str:
        """Navigates to `url` in a real browser and returns the fully
        rendered DOM's outerHTML.

        wait_selector: CSS selector to wait for before considering the page
            "loaded". Strongly preferred over a blind wait_ms.
        wait_ms: fallback/extra settle time after navigation.
        scroll: set True for infinite-scroll category pages.
        debug_save_path: if given, writes the raw rendered HTML to this
            local file path (relative to the current working directory)
            regardless of success/failure -- this is the fastest way to
            get real ground truth when a scraper keeps finding 0 links
            despite a regex already confirmed against real, verified
            product URLs (as happened live on Boohoo): open the saved
            file, search it for "/product" (or whatever pattern you'd
            expect), and paste back what's actually there instead of
            guessing again blind.
        """
        page = self.context.new_page()
        try:
            resp = page.goto(
                url, timeout=self.timeout_ms, wait_until="domcontentloaded", referer=referer
            )
            if resp is not None and resp.status == 403:
                raise ScraperError(
                    f"Blocked (403) even via real browser navigation: {url}. "
                    "This is a stronger signal than a plain httpx block -- "
                    "may need residential proxy / slower pacing / manual "
                    "cookie warm-up. Do not fabricate data -- report and stop."
                )

            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=self.timeout_ms)
                except Exception:
                    # Selector might legitimately not exist on this page
                    # (e.g. an out-of-stock product with a different
                    # layout) -- let the caller's parsing decide.
                    pass

            if scroll:
                for _ in range(6):
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(800)
                    except Exception:
                        # Page navigated away mid-scroll (e.g. redirected
                        # to a CAPTCHA/challenge page). Stop scrolling and
                        # fall through so the content-based block check
                        # below can raise a clean error instead of this
                        # crashing with a raw Playwright exception
                        # (confirmed live failure mode on SHEIN).
                        break

            page.wait_for_timeout(wait_ms)

            try:
                html = page.content()
            except Exception as e:
                raise ScraperError(
                    f"Could not read page content for {url} "
                    f"(page may have navigated away unexpectedly): {e}"
                )

            if debug_save_path:
                try:
                    with open(debug_save_path, "w", encoding="utf-8") as f:
                        f.write(html)
                    print(f"[debug] saved rendered HTML ({len(html)} chars) to {debug_save_path}", flush=True)
                except Exception as e:
                    print(f"[debug] could not save HTML to {debug_save_path}: {e}", flush=True)

            if check_blocked:
                lowered = html.lower()
                for marker in BLOCK_TEXT_MARKERS:
                    if marker in lowered:
                        raise ScraperError(
                            f"Bot-challenge / CAPTCHA page detected for {url} "
                            f"(matched marker: '{marker}'). Do not fabricate "
                            "data -- report and stop."
                        )

            return html
        finally:
            page.close()

    def download_image(self, image_url: str, category: str, product_code: str, suffix: str = "") -> Optional[str]:
        """Same contract as BaseScraper.download_image -- added here so
        every Playwright-based scraper (Zara, ASOS, SHEIN, Boohoo,
        Primark, Target) can actually save images, which it previously
        could not (this method simply didn't exist on this class).

        CONFIRMED LIVE FINDING: a plain httpx client downloading these
        same image URLs got 403 Forbidden / ReadTimeout on nearly every
        request from ASOS's image CDN -- while the exact same URLs load
        fine when hot-linked directly in a real browser (confirmed: the
        frontend was already displaying these images successfully via
        the image_url fallback, precisely because that request comes
        from a real browser tab, not a Python script). The fix is to
        make the "download" request through Playwright's own
        APIRequestContext (self.context.request), which shares the same
        browser context -- same TLS fingerprint, same cookies -- as the
        page navigations that already worked, instead of a separate,
        easily-fingerprinted plain httpx client.
        """
        if not image_url:
            return None
        try:
            resp = self.context.request.get(image_url, timeout=15000)
            if not resp.ok:
                raise RuntimeError(f"HTTP {resp.status} {resp.status_text}")
            content = resp.body()
        except Exception as e:
            if self._image_debug_remaining > 0:
                self._image_debug_remaining -= 1
                print(f"[{self.source_name}] image download failed: "
                      f"{image_url} -- {type(e).__name__}: {e}", flush=True)
            return None
        return save_image_bytes(content, self.source_name, category, product_code, image_url, suffix)

    def close(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()