"""
One-off cleanup for C&A cross-sell contamination -- see the fix in
app/scrapers/c_and_a.py's scrape_product() for the full story: C&A's
"Te podría gustar" recommendation widget leaks unrelated products
(including men's items) into a women's-only category scrape, and every
Data Collection entry for C&A only configures "mujer" URLs. Any C&A
product already in the database that's actually men's wear is leftover
contamination from before that fix existed.

Identifies contaminated rows via gender='MENS' (the gender classifier
already picks this up correctly from the product name -- see
gender_classify.py) AND, as a belt-and-suspenders check for anything the
classifier's name-based guess might have missed, a direct keyword scan
of the product name for men's-specific Spanish terms.

Safe to re-run: only rows matching one of these signals are touched.

Usage:
    cd backend
    python -m scripts.remove_c_and_a_mens_contamination
"""
import re

from app.database import SessionLocal, init_db
from app.models import Gender, Product

_MENS_NAME_HINTS = re.compile(r"\b(hombre|caballero)\b", re.IGNORECASE)


def cleanup():
    init_db()
    db = SessionLocal()
    try:
        rows = db.query(Product).filter(Product.source == "c_and_a").all()
        to_delete = [
            p for p in rows
            if p.gender == Gender.MENS or (p.product_name and _MENS_NAME_HINTS.search(p.product_name))
        ]

        if not to_delete:
            print("No C&A men's contamination found -- nothing to clean up.")
            return

        print(f"Removing {len(to_delete)} contaminated C&A product row(s):")
        for p in to_delete:
            print(f"  #{p.id}: {p.product_name}")
            db.delete(p)

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    cleanup()