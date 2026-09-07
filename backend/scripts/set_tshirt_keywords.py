"""
One-off: sets sanity_keywords on the T-shirt sub-category so link
discovery/parsing rejects known-bad nav links (the ones that don't
contain any t-shirt-related word) instead of silently saving them as
fake "products" now that the material/composition gate was relaxed.

Usage:
    cd backend
    python -m scripts.set_tshirt_keywords
"""
from sqlalchemy import text

from app.database import SessionLocal

db = SessionLocal()
try:
    db.execute(
        text("UPDATE item_hierarchy SET sanity_keywords = :kw WHERE id = 9"),
        {"kw": "camiseta,camisetas,polera,playera,t-shirt"},
    )
    db.commit()
    print("Done -- sub_category_id 9 (T shirt) now has sanity_keywords set.")
finally:
    db.close()