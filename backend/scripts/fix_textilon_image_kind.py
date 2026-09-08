"""One-off: fixes image_kind on the 30 Textilon rows imported before
the OUR_PRODUCT_IMAGE bug was caught -- purely cosmetic, safe to skip.

NOTE: products.image_kind is a native Postgres ENUM whose valid labels
are the ImageKind member NAMES ("COMPETITOR", "OUR_PRODUCT"), not their
.value strings ("COMPETITOR_IMAGE", "OUR_PRODUCT_IMAGE") -- SQLAlchemy
persists PEP-435 enums by name by default. Same mistake, same fix, as
the migrate_unify_and_add_gender.py bug from earlier in this project.

Usage: cd backend && python -m scripts.fix_textilon_image_kind
"""
from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()
try:
    result = db.execute(
        text("UPDATE products SET image_kind = 'OUR_PRODUCT' "
             "WHERE brand = 'Textilon' AND image_kind = 'COMPETITOR'")
    )
    db.commit()
    print(f"Fixed {result.rowcount} row(s).")
finally:
    db.close()