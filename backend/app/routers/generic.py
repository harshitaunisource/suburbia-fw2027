"""
Generic category explorer -- endpoints for the "brand setup" workflow:
add a buyer, add competitors to that buyer, add the category (item type
/ category / sub-category / gender) and the URL to scrape.

2026-09-07: `list_products` / `get_analytics` now query the unified
`Product` table (not `GenericProduct`) -- see models.py's notes. This
is what makes data scraped through this router show up on the classic
Products / Market Analytics / Buyer Opportunities pages too, since
those have always queried `Product`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, computed_field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Buyer,
    Gender,
    GenericScrapeRun,
    GenericSourceConfig,
    ItemHierarchy,
    Product,
    SourceRole,
)
from app.services.generic_scraper import DEFAULT_PDP_LINK_PATTERN, run_generic_scrape, scrape_single_product_url
from app.services.pricing import compute_mrp
from app.scrapers.base import ScraperError

router = APIRouter(prefix="/api/generic", tags=["generic"])


# ------------------------------------------------------------------ schemas
class HierarchyNode(BaseModel):
    id: int
    category: str
    sub_category: str


class CreateHierarchyRequest(BaseModel):
    item_type: str
    category: str
    sub_category: str
    sanity_keywords: Optional[str] = None


class HierarchyOut(BaseModel):
    id: int
    item_type: str
    category: str
    sub_category: str
    sanity_keywords: Optional[str] = None

    class Config:
        from_attributes = True


class BuyerOut(BaseModel):
    id: int
    name: str
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class CreateBuyerRequest(BaseModel):
    name: str
    notes: Optional[str] = None


class SourceConfigOut(BaseModel):
    id: int
    buyer_id: Optional[int] = None
    role: Optional[SourceRole] = None
    gender: Optional[Gender] = None
    sub_category_id: int
    brand: str
    category_url: str
    currency: str
    pdp_link_pattern: Optional[str] = None
    notes: Optional[str] = None
    item_type: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    buyer_name: Optional[str] = None

    class Config:
        from_attributes = True


class CreateSourceRequest(BaseModel):
    """The single endpoint behind the 'Add Brand' quick-add form.

    `gender` (added 2026-09-07): a real field distinguishing multiple
    source configs for the same brand + sub-category that are genuinely
    different product lines (e.g. a brand's Men's vs. Women's pajamas).
    Previously this had no dedicated field at all -- the only way to
    express it was smuggling it into the brand name or notes, which is
    exactly what caused a real collision between two Textilon sources
    sharing one (brand, sub_category) key.
    """
    brand: str
    category_url: str
    role: SourceRole = SourceRole.COMPETITOR
    gender: Optional[Gender] = None

    sub_category_id: Optional[int] = None
    item_type: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None

    buyer_id: Optional[int] = None
    buyer_name: Optional[str] = None

    # Manual fallback ONLY -- currency is now detected per-product from
    # the page itself (see app/scrapers/currency_detect.py). This value
    # is used only when a given product's page gives no usable signal.
    currency: str = "USD"
    # Optional override -- link discovery tries structural detection
    # first (see app/scrapers/link_discovery.py) and usually doesn't
    # need this at all.
    pdp_link_pattern: Optional[str] = None
    notes: Optional[str] = None


class UpdateSourceRequest(BaseModel):
    brand: Optional[str] = None
    category_url: Optional[str] = None
    role: Optional[SourceRole] = None
    gender: Optional[Gender] = None
    buyer_id: Optional[int] = None
    currency: Optional[str] = None
    pdp_link_pattern: Optional[str] = None
    notes: Optional[str] = None


class ProductOut(BaseModel):
    id: int
    product_uid: Optional[str] = None
    buyer_id: Optional[int] = None
    role: Optional[SourceRole] = None
    gender: Optional[Gender] = None
    brand: Optional[str]
    product_name: str
    product_url: str
    image_url: Optional[str]
    local_image_path: Optional[str]
    price: Optional[float]
    currency: Optional[str]
    original_price: Optional[float] = None
    material: Optional[str] = None
    pattern: Optional[str] = None
    color: Optional[str] = None

    class Config:
        from_attributes = True

    @computed_field
    @property
    def mrp(self) -> Optional[float]:
        return compute_mrp(self.price, self.original_price)


class ScrapeRunOut(BaseModel):
    id: int
    source_config_id: int
    status: str
    products_found: int
    products_new: int
    error_message: Optional[str] = None
    link_discovery_strategy: Optional[str] = None

    class Config:
        from_attributes = True


class TriggerScrapeRequest(BaseModel):
    source_config_id: int


class AddProductByUrlRequest(BaseModel):
    source_config_id: int
    product_url: str


def _hierarchy_label(db: Session, sub_category_id: int) -> dict:
    h = db.get(ItemHierarchy, sub_category_id)
    if not h:
        return {}
    return {"item_type": h.item_type, "category": h.category, "sub_category": h.sub_category}


def _source_out(db: Session, source: GenericSourceConfig) -> SourceConfigOut:
    buyer_name = None
    if source.buyer_id:
        buyer = db.get(Buyer, source.buyer_id)
        buyer_name = buyer.name if buyer else None
    return SourceConfigOut(
        id=source.id,
        buyer_id=source.buyer_id,
        role=source.role,
        gender=source.gender,
        sub_category_id=source.sub_category_id,
        brand=source.brand,
        category_url=source.category_url,
        currency=source.currency,
        pdp_link_pattern=source.pdp_link_pattern,
        notes=source.notes,
        buyer_name=buyer_name,
        **_hierarchy_label(db, source.sub_category_id),
    )


# ------------------------------------------------------------------ hierarchy
@router.get("/hierarchy")
def get_hierarchy(db: Session = Depends(get_db)):
    rows = db.query(ItemHierarchy).order_by(
        ItemHierarchy.item_type, ItemHierarchy.category, ItemHierarchy.sub_category
    ).all()

    tree: dict[str, dict[str, list[HierarchyNode]]] = {}
    for row in rows:
        tree.setdefault(row.item_type, {}).setdefault(row.category, []).append(
            HierarchyNode(id=row.id, category=row.category, sub_category=row.sub_category)
        )
    return tree


@router.get("/genders")
def list_genders():
    """Powers the Gender dropdown in Add Brand / Search Products --
    a fixed, small enum rather than free text, so it can't drift or be
    typo'd the way the old notes-field workaround could."""
    return [g.value for g in Gender]


@router.post("/hierarchy", response_model=HierarchyOut)
def create_hierarchy(req: CreateHierarchyRequest, db: Session = Depends(get_db)):
    existing = (
        db.query(ItemHierarchy)
        .filter(
            ItemHierarchy.item_type == req.item_type,
            ItemHierarchy.category == req.category,
            ItemHierarchy.sub_category == req.sub_category,
        )
        .first()
    )
    if existing:
        return existing

    row = ItemHierarchy(
        item_type=req.item_type,
        category=req.category,
        sub_category=req.sub_category,
        sanity_keywords=req.sanity_keywords,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ------------------------------------------------------------------ buyers
@router.get("/buyers", response_model=list[BuyerOut])
def list_buyers(db: Session = Depends(get_db)):
    return db.query(Buyer).order_by(Buyer.name).all()


@router.post("/buyers", response_model=BuyerOut)
def create_buyer(req: CreateBuyerRequest, db: Session = Depends(get_db)):
    existing = (
        db.query(Buyer).filter(Buyer.name.ilike(req.name.strip())).first()
    )
    if existing:
        return existing
    buyer = Buyer(name=req.name.strip(), notes=req.notes)
    db.add(buyer)
    db.commit()
    db.refresh(buyer)
    return buyer


@router.get("/buyers/{buyer_id}/sources", response_model=list[SourceConfigOut])
def list_buyer_sources(buyer_id: int, db: Session = Depends(get_db)):
    if not db.get(Buyer, buyer_id):
        raise HTTPException(status_code=404, detail="Buyer not found")
    sources = (
        db.query(GenericSourceConfig)
        .filter(GenericSourceConfig.buyer_id == buyer_id)
        .order_by(GenericSourceConfig.role, GenericSourceConfig.brand)
        .all()
    )
    return [_source_out(db, s) for s in sources]


# ------------------------------------------------------------------ sources
@router.get("/sources/unassigned", response_model=list[SourceConfigOut])
def list_unassigned_sources(db: Session = Depends(get_db)):
    sources = (
        db.query(GenericSourceConfig)
        .filter(GenericSourceConfig.buyer_id.is_(None))
        .order_by(GenericSourceConfig.brand)
        .all()
    )
    return [_source_out(db, s) for s in sources]


@router.get("/sources", response_model=list[SourceConfigOut])
def list_sources(
    sub_category_id: Optional[int] = None,
    buyer_id: Optional[int] = None,
    gender: Optional[Gender] = None,
    db: Session = Depends(get_db),
):
    q = db.query(GenericSourceConfig)
    if sub_category_id is not None:
        q = q.filter(GenericSourceConfig.sub_category_id == sub_category_id)
    if buyer_id is not None:
        q = q.filter(GenericSourceConfig.buyer_id == buyer_id)
    if gender is not None:
        q = q.filter(GenericSourceConfig.gender == gender)
    if sub_category_id is None and buyer_id is None:
        raise HTTPException(status_code=400, detail="Provide sub_category_id and/or buyer_id")
    return [_source_out(db, s) for s in q.all()]


@router.post("/sources", response_model=SourceConfigOut)
def create_source(req: CreateSourceRequest, db: Session = Depends(get_db)):
    sub_category_id = req.sub_category_id
    if sub_category_id is None:
        if not (req.item_type and req.category and req.sub_category):
            raise HTTPException(
                status_code=400,
                detail="Provide sub_category_id, or all of item_type/category/sub_category.",
            )
        hierarchy = (
            db.query(ItemHierarchy)
            .filter(
                ItemHierarchy.item_type == req.item_type,
                ItemHierarchy.category == req.category,
                ItemHierarchy.sub_category == req.sub_category,
            )
            .first()
        )
        if not hierarchy:
            hierarchy = ItemHierarchy(
                item_type=req.item_type, category=req.category, sub_category=req.sub_category
            )
            db.add(hierarchy)
            db.commit()
            db.refresh(hierarchy)
        sub_category_id = hierarchy.id
    elif not db.get(ItemHierarchy, sub_category_id):
        raise HTTPException(status_code=404, detail="sub_category_id not found")

    buyer_id = req.buyer_id
    role = req.role
    if buyer_id is None and req.buyer_name:
        buyer = db.query(Buyer).filter(Buyer.name.ilike(req.buyer_name.strip())).first()
        if not buyer:
            buyer = Buyer(name=req.buyer_name.strip())
            db.add(buyer)
            db.commit()
            db.refresh(buyer)
        buyer_id = buyer.id
    elif buyer_id is not None and not db.get(Buyer, buyer_id):
        raise HTTPException(status_code=404, detail="buyer_id not found")

    if buyer_id is None:
        role = None

    # Same-brand-same-category collision guard: if a source already
    # exists for this exact (brand, sub_category, gender), reuse it
    # instead of creating a duplicate that would split one brand's
    # products across two source rows. Without the gender clause here,
    # this is exactly the check that silently merged Textilon's men's
    # and women's pajamas before.
    existing = (
        db.query(GenericSourceConfig)
        .filter(
            GenericSourceConfig.sub_category_id == sub_category_id,
            GenericSourceConfig.brand.ilike(req.brand.strip()),
            GenericSourceConfig.gender == req.gender,
        )
        .first()
    )
    if existing:
        return _source_out(db, existing)

    source = GenericSourceConfig(
        sub_category_id=sub_category_id,
        buyer_id=buyer_id,
        role=role,
        gender=req.gender,
        brand=req.brand.strip(),
        category_url=req.category_url.strip(),
        currency=req.currency or "USD",
        pdp_link_pattern=req.pdp_link_pattern,
        notes=req.notes,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _source_out(db, source)


@router.patch("/sources/{source_id}", response_model=SourceConfigOut)
def update_source(source_id: int, req: UpdateSourceRequest, db: Session = Depends(get_db)):
    source = db.get(GenericSourceConfig, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    db.commit()
    db.refresh(source)
    return _source_out(db, source)


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.get(GenericSourceConfig, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    run_count = (
        db.query(GenericScrapeRun)
        .filter(GenericScrapeRun.source_config_id == source_id)
        .count()
    )
    # Checked against the unified `products` table now (new scrapes
    # land there) -- legacy generic_products rows for a source deleted
    # pre-migration are not double-counted since backfill only runs
    # once and only for URLs not already present.
    product_count = (
        db.query(Product)
        .filter(Product.source_config_id == source_id)
        .count()
    )
    if run_count or product_count:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Can't remove '{source.brand}' -- it has {run_count} scrape run(s) and "
                f"{product_count} product(s) already recorded against it. Removing it would "
                f"break that history. If you really want it gone, delete its scrape runs and "
                f"products first, or just leave it -- an unused duplicate source causes no harm."
            ),
        )

    db.delete(source)
    db.commit()
    return {"deleted": True}


# ------------------------------------------------------------------ scraping
@router.post("/scrape", response_model=ScrapeRunOut)
def trigger_scrape(req: TriggerScrapeRequest, db: Session = Depends(get_db)):
    source = db.get(GenericSourceConfig, req.source_config_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    run = run_generic_scrape(db, source)
    return run


@router.post("/products/add-by-url", response_model=ProductOut)
def add_product_by_url(req: AddProductByUrlRequest, db: Session = Depends(get_db)):
    """The 'browse the real site yourself, paste one product link'
    path -- for sites whose category page won't reliably render its
    product grid for an automated browser (confirmed live on Textilon).
    Scrapes exactly this one URL and saves it, reusing the same
    domain-aware parsing the category-driven flow uses."""
    source = db.get(GenericSourceConfig, req.source_config_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        product = scrape_single_product_url(db, source, req.product_url.strip())
    except ScraperError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return product


@router.get("/scrape-runs", response_model=list[ScrapeRunOut])
def list_scrape_runs(sub_category_id: int, db: Session = Depends(get_db)):
    return (
        db.query(GenericScrapeRun)
        .filter(GenericScrapeRun.sub_category_id == sub_category_id)
        .order_by(GenericScrapeRun.started_at.desc())
        .all()
    )


# ------------------------------------------------------------------ products
@router.get("/products", response_model=list[ProductOut])
def list_products(
    sub_category_id: int,
    brand: Optional[str] = None,
    buyer_id: Optional[int] = None,
    gender: Optional[Gender] = None,
    db: Session = Depends(get_db),
):
    """Reads from the unified `products` table (2026-09-07) -- anything
    scraped via Search Products / Explore Categories / Add Brand now
    lives here, same table the classic Products / Market Analytics /
    Buyer Opportunities pages already read."""
    q = db.query(Product).filter(Product.sub_category_id == sub_category_id)
    if brand:
        q = q.filter(Product.brand == brand)
    if buyer_id is not None:
        q = q.filter(Product.buyer_id == buyer_id)
    if gender is not None:
        q = q.filter(Product.gender == gender)
    return q.order_by(Product.scraped_at.desc()).all()


# ------------------------------------------------------------------ analytics
@router.get("/analytics")
def get_analytics(
    sub_category_id: int,
    brand: Optional[str] = None,
    buyer_id: Optional[int] = None,
    gender: Optional[Gender] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Product).filter(Product.sub_category_id == sub_category_id)
    if brand:
        q = q.filter(Product.brand == brand)
    if buyer_id is not None:
        q = q.filter(Product.buyer_id == buyer_id)
    if gender is not None:
        q = q.filter(Product.gender == gender)
    products = q.all()

    by_brand: dict[str, int] = {}
    by_currency: dict[str, list[float]] = {}
    for p in products:
        by_brand[p.brand or "unknown"] = by_brand.get(p.brand or "unknown", 0) + 1
        mrp = compute_mrp(p.price, p.original_price)
        if mrp:
            currency = p.currency or "USD"
            by_currency.setdefault(currency, []).append(mrp)

    price_distribution = {
        currency: {
            "min": round(min(prices), 2),
            "avg": round(sum(prices) / len(prices), 2),
            "max": round(max(prices), 2),
            "count": len(prices),
        }
        for currency, prices in by_currency.items()
    }

    return {
        "total_products": len(products),
        "by_brand": by_brand,
        "price_distribution": price_distribution,
    }