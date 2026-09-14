"""
Runs the Primark scraper directly from the terminal for both configured
categories (sweaters, blouses) -- the same underlying call the Data
Collection page's "Run Scraper" button makes (app.services.ingest.run_scrape),
just without needing the frontend/backend HTTP round-trip.

Requires a real internet connection to primark.com (this is an actual
Playwright browser scrape of the live site) -- it will not work from an
environment without outbound network access.

Usage:
    cd backend
    python -m scripts.run_primark_scrape
"""
from app.database import SessionLocal, init_db
from app.scrapers.primark import CATEGORY_URL_BLOUSES, CATEGORY_URL_SWEATERS
from app.services.ingest import run_scrape

CATEGORIES = [
    ("sweaters", CATEGORY_URL_SWEATERS),
    ("blouses", CATEGORY_URL_BLOUSES),
]


def main():
    init_db()
    db = SessionLocal()
    try:
        for category, url in CATEGORIES:
            print(f"\n=== Scraping primark / {category} ===")
            print(f"URL: {url}")
            run = run_scrape(db, source="primark", category=category, category_url=url)
            print(f"Status: {run.status}")
            if run.status == "failed":
                print(f"Error: {run.error_message}")
            else:
                print(
                    f"Found: {run.products_found}, "
                    f"New: {run.products_new}, Updated: {run.products_updated}, "
                    f"Images OK: {run.images_downloaded}, Images failed: {run.images_failed}"
                )
    finally:
        db.close()


if __name__ == "__main__":
    main()