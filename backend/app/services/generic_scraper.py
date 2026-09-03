"""
Phase for the generic category explorer: scrapes a single
GenericSourceConfig (one brand + category URL for one sub-category)
using the SAME proven building blocks already validated on the Suburbia
side of this project (Playwright rendering, OpenGraph/JSON-LD parsing,
category-sanity keyword filtering) -- rather than inventing new,
unverified logic.

HONESTY NOTE (read before adding a new source): there is no way to
reliably auto-discover "which links on this page are real products" for
an arbitrary, never-seen-before website without either (a) a
site-specific link pattern, or (b) real inspection of that site's HTML.
This project learned that lesson repeatedly and expensively on the
Suburbia side (Boohoo, SHEIN, Old Navy, Target all needed their
pdp_link_pattern corrected against real HTML before they worked, despite
each starting guess being individually reasonable). Adding a new brand
here follows the same loop:
  1. Add a GenericSourceConfig with a starting pdp_link_pattern (a
     reasonable generic default is offered, e.g. matching common
     "/product/", "/p/", "/dp/", "-p-\\d+" style URLs).
  2. Run it. If it finds 0 products, a debug HTML dump is saved
     (same mechanism as playwright_base.py's debug_save_path) --
     inspect it, find a real product link, and tighten the pattern.
  3. Re-run. This is expected to take one or two iterations per new
     brand, exactly like every Suburbia competitor scraper did.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from sqlalchemy.orm import Session

from app.models import GenericProduct, GenericScrapeRun, GenericSourceConfig, ItemHierarchy
from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers._generic_playwright_template import keywords_match
from app.scrapers.base import STORAGE_ROOT, ScraperError
from app.scrapers.playwright_base import PlaywrightScraper

# Reasonable generic starting guess for an unconfigured source -- matches
# the most common product-detail-page URL shapes seen across the sites
# already handled in this project (Target, SHEIN, Boohoo, ASOS, Zara all
# fall into one of these families). Still expect to need to tighten this
# per-site once you have real HTML to check it against.
DEFAULT_PDP_LINK_PATTERN = r'href="([^"]*(?:/product/|/p/|/dp/|-p-\d+)[^"]*)"'


def run_generic_scrape(db: Session, source_config: GenericSourceConfig, max_products: int = 60) -> GenericScrapeRun:
    hierarchy: ItemHierarchy = db.get(ItemHierarchy, source_config.sub_category_id)
    run = GenericScrapeRun(
        sub_category_id=source_config.sub_category_id,
        source_config_id=source_config.id,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    pattern = source_config.pdp_link_pattern or DEFAULT_PDP_LINK_PATTERN
    keywords = [k.strip() for k in (hierarchy.sanity_keywords or "").split(",") if k.strip()]

    scraper = PlaywrightScraper()
    scraper.source_name = f"generic-{source_config.brand}"
    try:
        try:
            debug_path = f"generic_{source_config.brand}_{hierarchy.sub_category}_debug.html".replace(" ", "_")
            html = scraper.get_rendered_html(
                source_config.category_url, wait_ms=4000, scroll=True, debug_save_path=debug_path
            )
            links = sorted(set(re.findall(pattern, html)))
            print(f"[generic:{source_config.brand}] found {len(links)} candidate links "
                  f"(debug HTML saved to {debug_path})", flush=True)

            if not links:
                raise ScraperError(
                    f"No links matched pdp_link_pattern on {source_config.category_url}. "
                    f"Inspect {debug_path} for real product link examples and update "
                    f"this source's pdp_link_pattern via the API."
                )

            product_urls = [urljoin(source_config.category_url, link) for link in links][:max_products]

            found = new_count = images_ok = images_failed = 0
            for i, purl in enumerate(product_urls, start=1):
                try:
                    product_html = scraper.get_rendered_html(purl, wait_selector="h1", wait_ms=1500)
                    parsed = parse_generic_product(
                        product_html, purl, source_config.brand, brand=source_config.brand,
                        category_hint=None, currency=source_config.currency or "USD",
                    )
                    # Category-sanity check against this sub-category's
                    # own auto-derived (or edited) keyword list -- same
                    # defensive pattern already proven necessary on the
                    # Suburbia side (caught real contamination live on
                    # Target: a patio-furniture link that slipped into a
                    # "blouses" category grid).
                    if keywords:
                        text = f"{parsed.product_name} {parsed.description or ''}"
                        if not keywords_match(text, keywords):
                            print(f"[generic:{source_config.brand}] ({i}/{len(product_urls)}) SKIP "
                                  f"(no {hierarchy.sub_category} keyword match): {parsed.product_name}", flush=True)
                            continue

                    # Mandatory-fields rule (explicit project requirement):
                    # composition, price, image, and name are required for
                    # a product to be usable. Skip (don't save) anything
                    # missing one of these, rather than saving an
                    # incomplete row that would silently fail later
                    # analysis or export.
                    missing = []
                    if not parsed.material:
                        missing.append("composition")
                    if not parsed.price:
                        missing.append("price")
                    if not parsed.image_url:
                        missing.append("image")
                    if not parsed.product_name:
                        missing.append("name")
                    if missing:
                        print(f"[generic:{source_config.brand}] ({i}/{len(product_urls)}) SKIP "
                              f"(missing mandatory field(s): {', '.join(missing)}): {parsed.product_name}", flush=True)
                        continue

                    local_path = None
                    if parsed.image_url:
                        local_path = scraper.download_image(
                            parsed.image_url, f"generic/{hierarchy.id}", parsed.product_code or f"item{i}"
                        )
                        images_ok += 1 if local_path else 0
                        images_failed += 0 if local_path else 1

                    existing = (
                        db.query(GenericProduct)
                        .filter(GenericProduct.product_url == purl)
                        .first()
                    )
                    if existing:
                        continue
                    db.add(
                        GenericProduct(
                            product_uid=str(uuid.uuid4()),
                            sub_category_id=source_config.sub_category_id,
                            source_config_id=source_config.id,
                            buyer_id=source_config.buyer_id,      # new
                            role=source_config.role, 
                            brand=source_config.brand,
                            product_name=parsed.product_name,
                            product_code=parsed.product_code,
                            product_url=purl,
                            image_url=parsed.image_url,
                            local_image_path=local_path,
                            price=parsed.price,
                            original_price=parsed.original_price,
                            currency=parsed.currency,
                            material=parsed.material,
                            description=parsed.description,
                        )
                    )
                    found += 1
                    new_count += 1
                    print(f"[generic:{source_config.brand}] ({i}/{len(product_urls)}) OK: {parsed.product_name}", flush=True)
                except ScraperError as e:
                    print(f"[generic:{source_config.brand}] ({i}/{len(product_urls)}) SKIP: {e}", flush=True)
                    continue
                except Exception as e:
                    print(f"[generic:{source_config.brand}] ({i}/{len(product_urls)}) SKIP (unexpected): {e}", flush=True)
                    continue

            db.commit()
            run.status = "success"
            run.products_found = found
            run.products_new = new_count
            run.images_downloaded = images_ok
            run.images_failed = images_failed
            run.finished_at = datetime.utcnow()
            db.commit()
            return run

        except ScraperError as e:
            run.status = "failed"
            run.error_message = str(e)
            run.finished_at = datetime.utcnow()
            db.commit()
            return run
        except Exception as e:
            run.status = "failed"
            run.error_message = f"Unexpected error: {e}"
            run.finished_at = datetime.utcnow()
            db.commit()
            return run
    finally:
        try:
            scraper.close()
        except Exception:
            pass