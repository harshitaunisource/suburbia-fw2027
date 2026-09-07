"""
Phase for the category explorer: scrapes a single GenericSourceConfig
(one brand + category URL + gender for one sub-category).

2026-09-07 REWRITE -- three structural changes, no AI/LLM involved in
any of them:

  1. Link discovery no longer relies on a single hand-tuned regex as
     the primary mechanism. app/scrapers/link_discovery.py tries (a) the
     category page's own JSON-LD ItemList, then (b) structural URL-shape
     clustering, then (c) a configured override, then (d) the old
     generic default regex -- in that order. A brand's
     `pdp_link_pattern` is still honored if set, but it's no longer the
     only way forward when it's missing or wrong.

  2. Products are written into the unified `Product` table (not the
     separate GenericProduct table) -- see models.py's 2026-09-07 notes.
     This is what makes anything scraped here show up on the classic
     Products page, Market Analytics, and Buyer Opportunities without
     any extra step. `role`/`buyer_id`/`sub_category_id`/`gender` ride
     along on the same row Product.category/subcategory always had.

  3. `gender` (from the source config) is stamped onto every product
     this run produces -- this is what actually prevents a Textilon
     men's/women's collision going forward: the two source configs are
     distinguished by gender, so their products never merge into one
     undifferentiated pile.

Currency is no longer taken as-is from the source config -- it's
detected per-product from the page itself (see currency_detect.py
via parse_generic_product); the config's `currency` field is only the
last-resort fallback when the page gives no signal at all.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import GenericScrapeRun, GenericSourceConfig, ItemHierarchy, Product
from app.scrapers._generic_playwright_template import parse_generic_product
from app.scrapers._generic_playwright_template import (
    category_wait_hidden_for, category_wait_until_for, keywords_match, wait_ms_for, wait_selector_for,
)
from app.scrapers.base import STORAGE_ROOT, ScraperError
from app.scrapers.link_discovery import DEFAULT_PDP_LINK_PATTERN, discover_product_links
from app.scrapers.playwright_base import PlaywrightScraper

__all__ = ["DEFAULT_PDP_LINK_PATTERN", "run_generic_scrape", "scrape_single_product_url"]


def scrape_single_product_url(db: Session, source_config: GenericSourceConfig, product_url: str) -> Product:
    """Scrapes exactly ONE product page and saves it -- no category-page
    fetch, no link discovery at all. This is the 'paste a link you found
    by browsing the site normally' path: for a site whose category page
    won't reliably render its product grid for an automated browser
    (confirmed live on Textilon -- the category page's product grid
    stays empty even after networkidle + waiting for the loading spinner
    to disappear), a person can still browse the real site in their own
    browser, copy a product's URL, and add it directly -- reusing the
    exact same domain-override-aware parsing (title selector, wait
    time, currency detection, etc.) that the category-driven flow uses,
    just without needing link discovery to have found it first.
    """
    hierarchy: ItemHierarchy = db.get(ItemHierarchy, source_config.sub_category_id)
    category_value = hierarchy.sub_category.lower()

    existing = db.query(Product).filter(Product.product_url == product_url).first()
    if existing:
        return existing

    scraper = PlaywrightScraper()
    scraper.source_name = f"generic-{source_config.brand}"
    try:
        product_html = scraper.get_rendered_html(
            product_url,
            wait_selector=wait_selector_for(product_url),
            wait_ms=wait_ms_for(product_url, default=1500),
            debug_save_path=f"generic_{source_config.brand}_single_product_debug.html".replace(" ", "_"),
        )
        parsed = parse_generic_product(
            product_html, product_url, source_config.brand, brand=source_config.brand,
            # No category_hint here on purpose: this is a URL a human
            # deliberately picked by browsing the real site themselves,
            # so the automatic "does this look like the right category"
            # sanity check (built to catch bad LINK DISCOVERY guesses)
            # doesn't apply -- trust the person's own click.
            category_hint=None, currency=source_config.currency or "USD",
        )

        if not parsed.product_name or not parsed.image_url:
            raise ScraperError(
                f"Could not find a name and image for {product_url} -- open the debug HTML "
                f"file just saved to see what actually rendered."
            )

        local_path = None
        if parsed.image_url:
            local_path = scraper.download_image(
                parsed.image_url, f"generic/{hierarchy.id}", parsed.product_code or "item"
            )

        product = Product(
            product_uid=str(uuid.uuid4()),
            source=f"{source_config.brand.lower().replace(' ', '_')}",
            brand=source_config.brand,
            category=category_value,
            subcategory=hierarchy.category,
            sub_category_id=source_config.sub_category_id,
            source_config_id=source_config.id,
            buyer_id=source_config.buyer_id,
            role=source_config.role,
            gender=source_config.gender,
            product_name=parsed.product_name,
            product_code=parsed.product_code,
            product_url=product_url,
            image_url=parsed.image_url,
            local_image_path=local_path,
            price=parsed.price,
            original_price=parsed.original_price,
            discount_price=parsed.discount_price,
            discount_percentage=parsed.discount_percentage,
            currency=parsed.currency,
            material=parsed.material,
            color=(parsed.colors[0] if parsed.colors else None),
            description=parsed.description,
            availability=parsed.availability,
            scraped_at=datetime.utcnow(),
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
    finally:
        try:
            scraper.close()
        except Exception:
            pass


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

    keywords = [k.strip() for k in (hierarchy.sanity_keywords or "").split(",") if k.strip()]
    # Consistent with how Suburbia's own scrapers populate Product.category
    # (lowercase sub-category name, e.g. "sweaters") -- keeps the shared
    # CATEGORY_SANITY_KEYWORDS lookup and existing category filters
    # working the same way for both product sources.
    category_value = hierarchy.sub_category.lower()

    scraper = PlaywrightScraper()
    scraper.source_name = f"generic-{source_config.brand}"
    try:
        try:
            debug_path = f"generic_{source_config.brand}_{hierarchy.sub_category}_debug.html".replace(" ", "_")
            html = scraper.get_rendered_html(
                source_config.category_url,
                wait_ms=wait_ms_for(source_config.category_url, default=4000),
                scroll=True,
                debug_save_path=debug_path,
                wait_until=category_wait_until_for(source_config.category_url),
                # See category_wait_hidden_for's docstring: for sites
                # where the product grid finishes rendering AFTER the
                # network itself goes idle (confirmed live on Textilon),
                # this waits for the actual loading-spinner element to
                # disappear -- a direct signal instead of an indirect
                # one. None for sites with no configured override, in
                # which case this is simply a no-op.
                wait_selector_hidden=category_wait_hidden_for(source_config.category_url),
            )

            product_urls, strategy = discover_product_links(
                html,
                base_url=source_config.category_url,
                configured_pattern=source_config.pdp_link_pattern,
                max_links=max_products,
            )
            run.link_discovery_strategy = strategy
            db.commit()
            print(
                f"[generic:{source_config.brand}] found {len(product_urls)} candidate links "
                f"via '{strategy}' (debug HTML saved to {debug_path})",
                flush=True,
            )
            for u in product_urls:
                print(f"[generic:{source_config.brand}]   candidate: {u}", flush=True)

            if not product_urls:
                raise ScraperError(
                    f"No product links found on {source_config.category_url} using any discovery "
                    f"strategy (JSON-LD ItemList, structural URL clustering, configured pattern, "
                    f"or the generic default). Inspect {debug_path} -- if this site genuinely uses "
                    f"an unusual link shape, set pdp_link_pattern on this source as a manual override."
                )

            found = new_count = images_ok = images_failed = 0
            for i, purl in enumerate(product_urls, start=1):
                try:
                    product_html = scraper.get_rendered_html(
                        purl,
                        wait_selector=wait_selector_for(purl),
                        wait_ms=wait_ms_for(purl, default=1500),
                    )
                    parsed = parse_generic_product(
                        product_html, purl, source_config.brand, brand=source_config.brand,
                        category_hint=category_value, currency=source_config.currency or "USD",
                    )

                    if keywords:
                        text = f"{parsed.product_name} {parsed.description or ''}"
                        if not keywords_match(text, keywords):
                            print(f"[generic:{source_config.brand}] ({i}/{len(product_urls)}) SKIP "
                                  f"(no {hierarchy.sub_category} keyword match): {parsed.product_name}", flush=True)
                            continue

                    # Only name + image + link are truly required for a
                    # catalogue/PPT picker (which is what this actually
                    # feeds -- see the routers/frontend pages). Price is
                    # kept as a soft "nice to have" (shown when present,
                    # never blocks a save). Composition/material is NOT
                    # required at all anymore -- plenty of real product
                    # pages simply don't expose it in scrapeable text
                    # (behind an accordion, a PDF spec sheet, etc.), and
                    # requiring it was silently discarding real, usable
                    # products that had a perfectly good name/image/price.
                    missing = []
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
                        db.query(Product)
                        .filter(Product.product_url == purl)
                        .first()
                    )
                    if existing:
                        continue

                    db.add(
                        Product(
                            product_uid=str(uuid.uuid4()),
                            source=f"{source_config.brand.lower().replace(' ', '_')}",
                            brand=source_config.brand,
                            category=category_value,
                            subcategory=hierarchy.category,
                            sub_category_id=source_config.sub_category_id,
                            source_config_id=source_config.id,
                            buyer_id=source_config.buyer_id,
                            role=source_config.role,
                            gender=source_config.gender,
                            product_name=parsed.product_name,
                            product_code=parsed.product_code,
                            product_url=purl,
                            image_url=parsed.image_url,
                            local_image_path=local_path,
                            price=parsed.price,
                            original_price=parsed.original_price,
                            discount_price=parsed.discount_price,
                            discount_percentage=parsed.discount_percentage,
                            currency=parsed.currency,
                            material=parsed.material,
                            color=(parsed.colors[0] if parsed.colors else None),
                            description=parsed.description,
                            availability=parsed.availability,
                            scraped_at=datetime.utcnow(),
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
            # Roll back first: if the commit right above this failed
            # (e.g. the DB connection was dropped mid-run -- confirmed
            # live via a Neon "server closed the connection
            # unexpectedly" after a long scrape), the session is left in
            # an aborted-transaction state. Committing again without
            # rolling back first raises PendingRollbackError, which was
            # uncaught and crashed the whole request into a raw 500
            # instead of a normal "failed" run result.
            db.rollback()
            run.status = "failed"
            run.error_message = str(e)
            run.finished_at = datetime.utcnow()
            db.commit()
            return run
        except Exception as e:
            db.rollback()
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