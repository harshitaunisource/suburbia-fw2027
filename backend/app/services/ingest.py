from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Product, ScrapeRun
from app.scrapers.base import ScrapedProduct, ScraperError
from app.scrapers.registry import get_scraper


def run_scrape(db: Session, source: str, category: str, category_url: str, max_pages: int | None = None) -> ScrapeRun:
    run = ScrapeRun(source=source, category=category, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    scraper = get_scraper(source)
    try:
        try:
            scraped = scraper.scrape_category(category_url, max_pages=max_pages)
        except ScraperError as e:
            run.status = "failed"
            run.error_message = str(e)
            run.finished_at = datetime.utcnow()
            db.commit()
            return run
        except Exception as e:
            # Any OTHER unexpected exception (a library bug, a site
            # returning a shape the parser didn't anticipate, etc.) must
            # still be recorded as a normal failed run -- never left to
            # propagate uncaught. Previously this branch didn't exist,
            # which combined with a since-fixed bug (two separate,
            # unrelated ScraperError classes -- see base.py's docstring)
            # meant Playwright-based scrapers' failures skipped straight
            # past the `except ScraperError` above, so `scraper.close()`
            # below never ran, leaking the browser process into the next
            # scrape in the same process and crashing it with an
            # unrelated-looking "Sync API inside the asyncio loop" error.
            run.status = "failed"
            run.error_message = f"Unexpected error (not a normal ScraperError): {e}"
            run.finished_at = datetime.utcnow()
            db.commit()
            return run

        new_count = updated_count = dup_count = images_ok = images_failed = 0

        total_items = len(scraped)
        print(f"[ingest] {source}/{category}: downloading images for {total_items} products...", flush=True)

        for idx, item in enumerate(scraped, start=1):
            existing = (
                db.query(Product)
                .filter(Product.source == item.source, Product.product_code == item.product_code)
                .first()
            )

            local_path = None
            if item.image_url:
                try:
                    local_path = scraper.download_image(item.image_url, item.category, item.product_code or "unknown")
                except Exception:
                    # A single bad image download must never abort the
                    # whole scrape -- count it as failed and move on.
                    local_path = None
                if local_path:
                    images_ok += 1
                else:
                    images_failed += 1
                # PROGRESS LOGGING: this loop was completely silent before,
                # so a run that was actually just downloading 65+ images
                # one by one (each with its own network round-trip) looked
                # identical to a genuine hang, with nothing in the DB and
                # nothing on the frontend until the whole batch committed
                # at the end. Print one line every few items so it's clear
                # this is progressing.
                if idx % 5 == 0 or idx == total_items:
                    print(f"[ingest] {source}/{category}: images {idx}/{total_items} "
                          f"(ok={images_ok}, failed={images_failed})", flush=True)

            if existing:
                _apply(existing, item, local_path)
                updated_count += 1
            else:
                product = Product()
                _apply(product, item, local_path)
                product.created_at = datetime.utcnow()
                db.add(product)
                new_count += 1

        db.commit()

        run.finished_at = datetime.utcnow()
        run.status = "success"
        run.products_found = len(scraped)
        run.products_new = new_count
        run.products_updated = updated_count
        run.duplicates_skipped = dup_count
        run.images_downloaded = images_ok
        run.images_failed = images_failed
        db.commit()

        return run
    finally:
        # CRITICAL: always release the scraper's resources -- the httpx
        # client for BaseScraper-based scrapers, or the real browser
        # process + its own event loop for PlaywrightScraper-based ones --
        # no matter how the block above exited (success, ScraperError, or
        # an unexpected exception). Skipping this on the failure paths
        # was the root cause of one failed Playwright scrape crashing the
        # very next one run in the same process.
        try:
            scraper.close()
        except Exception:
            pass


def _apply(product: Product, item: ScrapedProduct, local_image_path: str | None):
    product.source = item.source
    product.brand = item.brand
    product.category = item.category
    product.subcategory = item.subcategory
    product.product_name = item.product_name
    product.product_code = item.product_code
    product.product_url = item.product_url
    product.image_url = item.image_url
    product.local_image_path = local_image_path
    product.price = item.price
    product.currency = item.currency
    product.original_price = item.original_price
    product.discount_price = item.discount_price
    product.discount_percentage = item.discount_percentage
    product.description = item.description
    product.material = item.material
    product.sizes = ",".join(item.sizes) if item.sizes else None
    product.colors = ",".join(item.colors) if item.colors else None
    product.availability = item.availability
    product.scraped_at = datetime.utcnow()
    product.updated_at = datetime.utcnow()
    # image_kind defaults to COMPETITOR_IMAGE for every scraped product;
    # Suburbia's own products are still "source data", not our catalogue art,
    # so they stay COMPETITOR_IMAGE too (never auto-promoted to OUR_PRODUCT).