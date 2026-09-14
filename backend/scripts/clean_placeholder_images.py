"""
One-off cleanup for a real, confirmed-live scraper bug: when a page's
og:image meta tag itself pointed at the site's own "no image available"
placeholder graphic (confirmed on Primark: every product's og:image was
literally ".../assets/images/no-image.png") and the JSON-LD fallback also
had nothing usable, the scraper kept storing that placeholder URL as if
it were a real product photo instead of leaving image_url empty. Fixed
going forward in app/scrapers/_generic_playwright_template.py -- this
script cleans up whatever was already stored before that fix.

Nulls out image_url (and local_image_path, if a copy of the placeholder
graphic was downloaded) for any row whose image_url matches one of the
known placeholder markers. Does not delete the product row itself, just
clears the bad image reference so the UI correctly falls back to "No
image" instead of rendering the placeholder graphic.

Safe to re-run: only touches rows that still match a placeholder marker.

Usage:
    cd backend
    python -m scripts.clean_placeholder_images
"""
from sqlalchemy import text

from app.database import SessionLocal, init_db

PLACEHOLDER_MARKERS = ["no-image", "placeholder", "default-image", "noimage"]


def cleanup():
    init_db()
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT id, source, image_url FROM products WHERE image_url IS NOT NULL")
        ).fetchall()

        to_clear = [
            row_id for row_id, source, image_url in rows
            if image_url and any(marker in image_url.lower() for marker in PLACEHOLDER_MARKERS)
        ]

        if not to_clear:
            print("No products rows have a placeholder image_url -- nothing to clean up.")
            return

        by_source: dict[str, int] = {}
        for row_id, source, image_url in rows:
            if row_id in to_clear:
                by_source[source] = by_source.get(source, 0) + 1

        print(f"Clearing placeholder image_url on {len(to_clear)} row(s):")
        for source, count in sorted(by_source.items(), key=lambda kv: -kv[1]):
            print(f"  {source}: {count}")

        placeholders = ", ".join(f":id{i}" for i in range(len(to_clear)))
        params = {f"id{i}": row_id for i, row_id in enumerate(to_clear)}
        db.execute(
            text(
                f"UPDATE products SET image_url = NULL, local_image_path = NULL "
                f"WHERE id IN ({placeholders})"
            ),
            params,
        )
        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    cleanup()