import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Product, ScrapeRun
from app.scrapers.base import ScrapedProduct, ScraperError
from app.scrapers.registry import get_scraper


def _safe_commit(db: Session):
    """Wraps db.commit() so a failed-status write can never itself crash
    the whole run -- confirmed live: a stale/dropped connection (Neon's
    free-tier pooler closing an idle connection during a long browser-
    based scrape) caused THIS commit to itself throw
    psycopg2.OperationalError, obscuring the real error behind a
    confusing database crash. pool_pre_ping (see database.py) prevents
    most of this, but isn't airtight against every timing window."""
    try:
        db.commit()
    except Exception as e:
        print(f"[ingest] WARNING: could not write failure status to the database "
              f"(the actual scrape failure reason above is still the real one): {e}", flush=True)
        try:
            db.rollback()
        except Exception:
            pass


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
            _safe_commit(db)
            return run
        except Exception as e:
            run.status = "failed"
            run.error_message = f"Unexpected error (not a normal ScraperError): {e}"
            run.finished_at = datetime.utcnow()
            _safe_commit(db)
            return run

        new_count = updated_count = dup_count = images_ok = images_failed = 0

        total_items = len(scraped)
        print(f"[ingest] {source}/{category}: downloading images for {total_items} products...", flush=True)

        for idx, item in enumerate(scraped, start=1):
            try:
                existing = (
                    db.query(Product)
                    .filter(Product.source == item.source, Product.product_code == item.product_code)
                    .first()
                )
            except Exception as e:
                print(f"[ingest] WARNING: lookup query failed ({e}), retrying once after rollback...", flush=True)
                try:
                    db.rollback()
                except Exception:
                    pass
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
                    local_path = None
                if local_path:
                    images_ok += 1
                else:
                    images_failed += 1
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

            if idx % 5 == 0 or idx == total_items:
                _safe_commit(db)

        run.finished_at = datetime.utcnow()
        run.status = "success"
        run.products_found = len(scraped)
        run.products_new = new_count
        run.products_updated = updated_count
        run.duplicates_skipped = dup_count
        run.images_downloaded = images_ok
        run.images_failed = images_failed
        _safe_commit(db)

        return run
    finally:
        try:
            scraper.close()
        except Exception:
            pass


def _apply(product: Product, item: ScrapedProduct, local_image_path: str | None):
    if not product.product_uid:
        product.product_uid = str(uuid.uuid4())
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