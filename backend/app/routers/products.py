from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product
from app.schemas import ProductOut

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    brand: str | None = None,
    category: str | None = None,
    source: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    q = db.query(Product)
    if brand:
        q = q.filter(Product.brand == brand)
    if category:
        q = q.filter(Product.category == category)
    if source:
        q = q.filter(Product.source == source)
    if price_min is not None:
        q = q.filter(Product.price >= price_min)
    if price_max is not None:
        q = q.filter(Product.price <= price_max)
    return q.order_by(Product.scraped_at.desc()).offset(offset).limit(limit).all()


@router.get("/meta/categories")
def list_categories(db: Session = Depends(get_db)):
    """Every category that has at least one scraped product -- powers
    the category dropdown on Buyer Opportunities / Market Analytics so
    it reflects what's actually been scraped instead of a hardcoded
    list that goes stale the moment a new category is added."""
    rows = (
        db.query(Product.category)
        .filter(Product.category.isnot(None))
        .distinct()
        .order_by(Product.category)
        .all()
    )
    return [r[0] for r in rows]


@router.get("/meta/sources")
def list_sources(category: str | None = None, db: Session = Depends(get_db)):
    """Every distinct source ('suburbia', 'zara', 'women_secret', ...)
    that has scraped products, optionally narrowed to one category.
    Powers the buyer/competitor and brand multi-select dropdowns --
    these lists grow automatically as new brands get scraped, no code
    change needed."""
    q = db.query(Product.source).filter(Product.source.isnot(None)).distinct()
    if category:
        q = q.filter(Product.category == category)
    return sorted(r[0] for r in q.all())


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    return db.query(Product).get(product_id)