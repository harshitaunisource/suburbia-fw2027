"""
Generic category explorer -- endpoints for the standalone "brand setup"
workflow: add a buyer, add competitors to that buyer, add the category
(item type / category / sub-category) and the URL to scrape, all as data
through this API instead of code edits. Completely separate from every
existing Suburbia FW2027 endpoint: different tables, different services,
no shared code paths that could let a bug here affect the original
gap-analysis feature (or vice versa).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, computed_field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Buyer,
    GenericProduct,
    GenericScrapeRun,
    GenericSourceConfig,
    ItemHierarchy,
    SourceRole,
)
from app.services.generic_scraper import DEFAULT_PDP_LINK_PATTERN, run_generic_scrape
from app.services.pricing import compute_mrp

router = APIRouter(prefix="/api/generic", tags=["generic"])


# ------------------------------------------------------------------ schemas
class HierarchyNode(BaseModel):
    id: int
    category: str
    sub_category: str


class CreateHierarchyRequest(BaseModel):
    """Used by the 'Add Brand' form when the item/category/sub-category
    a person types doesn't already exist in the dropdowns -- lets a
    non-technical user add a brand-new category on the spot instead of
    being blocked until someone edits the hierarchy sheet."""
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
    sub_category_id: int
    brand: str
    category_url: str
    currency: str
    pdp_link_pattern: Optional[str] = None
    notes: Optional[str] = None
    # Denormalized for display so the frontend never has to do its own
    # join just to show "Zara -- GARMENT / APPAREL / Sweaters".
    item_type: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    buyer_name: Optional[str] = None

    class Config:
        from_attributes = True


class CreateSourceRequest(BaseModel):
    """The single endpoint behind the 'Add Brand' quick-add form: type a
    brand name + URL, pick (or create) the category, pick (or create) the
    buyer, say whether this URL is the buyer's own site or a competitor's.

    Category can be given either as an existing sub_category_id, or as
    (item_type, category, sub_category) text to find-or-create -- so the
    form works whether or not the exact row already exists.

    Buyer can be given either as an existing buyer_id, or as a new
    buyer_name to find-or-create -- so adding the very first source for a
    brand-new buyer doesn't require a separate step first.
    """
    brand: str
    category_url: str
    role: SourceRole = SourceRole.COMPETITOR

    sub_category_id: Optional[int] = None
    item_type: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None

    buyer_id: Optional[int] = None
    buyer_name: Optional[str] = None

    currency: str = "USD"
    pdp_link_pattern: Optional[str] = None
    notes: Optional[str] = None


class UpdateSourceRequest(BaseModel):
    brand: Optional[str] = None
    category_url: Optional[str] = None
    role: Optional[SourceRole] = None
    buyer_id: Optional[int] = None
    currency: Optional[str] = None
    pdp_link_pattern: Optional[str] = None
    notes: Optional[str] = None


class ProductOut(BaseModel):
    id: int
    product_uid: Optional[str] = None
    buyer_id: Optional[int] = None
    role: Optional[SourceRole] = None
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
        """Same rule as the Suburbia-side ProductOut.mrp: the only price
        figure any consumer should display, never a discounted price."""
        return compute_mrp(self.price, self.original_price)


class ScrapeRunOut(BaseModel):
    id: int
    source_config_id: int
    status: str
    products_found: int
    products_new: int
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class TriggerScrapeRequest(BaseModel):
    source_config_id: int


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
    """Returns the full Item Type -> Category -> Sub Category tree for
    the three cascading dropdowns."""
    rows = db.query(ItemHierarchy).order_by(
        ItemHierarchy.item_type, ItemHierarchy.category, ItemHierarchy.sub_category
    ).all()

    tree: dict[str, dict[str, list[HierarchyNode]]] = {}
    for row in rows:
        tree.setdefault(row.item_type, {}).setdefault(row.category, []).append(
            HierarchyNode(id=row.id, category=row.category, sub_category=row.sub_category)
        )
    return tree


@router.post("/hierarchy", response_model=HierarchyOut)
def create_hierarchy(req: CreateHierarchyRequest, db: Session = Depends(get_db)):
    """Find-or-create: if this exact (item_type, category, sub_category)
    already exists, returns the existing row instead of making a
    duplicate -- so a person re-typing an existing category by hand in
    the 'Add Brand' form doesn't fork the dropdown list."""
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
    """Find-or-create by name (case-insensitive) so re-submitting the
    same buyer name from the quick-add form is a no-op, not a duplicate
    buyer with the same name."""
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
    """Every source (the buyer's own + all its competitors) across every
    category -- this is what the 'Brand Setup' master-data page shows per
    buyer."""
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
    """Every source with no buyer yet -- brands/URLs pulled in via the
    standalone Search Products page. Brand Setup's 'add competitor' /
    'add buyer' form offers these in a dropdown so a brand that's already
    been searched can be attached to a buyer directly, instead of
    re-entering its brand name and URL and creating a duplicate row."""
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
    db: Session = Depends(get_db),
):
    q = db.query(GenericSourceConfig)
    if sub_category_id is not None:
        q = q.filter(GenericSourceConfig.sub_category_id == sub_category_id)
    if buyer_id is not None:
        q = q.filter(GenericSourceConfig.buyer_id == buyer_id)
    if sub_category_id is None and buyer_id is None:
        raise HTTPException(status_code=400, detail="Provide sub_category_id and/or buyer_id")
    return [_source_out(db, s) for s in q.all()]


@router.post("/sources", response_model=SourceConfigOut)
def create_source(req: CreateSourceRequest, db: Session = Depends(get_db)):
    """The endpoint behind the 'Add Brand' quick-add form. See
    CreateSourceRequest's docstring for how category/buyer resolution
    works."""
    # Resolve (or create) the category.
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

    # Resolve (or create) the buyer -- optional. Leaving both buyer_id
    # and buyer_name empty is valid and intentional: this is what the
    # standalone Search Products page does (just pull data for a
    # brand+category, without deciding yet whether it's a buyer's own
    # site or a competitor's). Brand Setup's "add competitor/buyer" flow
    # can attach it to a real buyer later via PATCH instead of creating
    # a duplicate source.
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
        # No buyer attached yet -- role is meaningless without one.
        role = None

    source = GenericSourceConfig(
        sub_category_id=sub_category_id,
        buyer_id=buyer_id,
        role=role,
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

    # A source with scrape history can't be deleted outright -- it's
    # referenced by generic_scrape_runs / generic_products via
    # source_config_id, and the database (correctly) refuses to delete a
    # row something else still points at. Rather than let that surface as
    # a raw 500 (which is what happened with the one-off cleanup script
    # against this exact situation), check up front and return a clear,
    # actionable message instead.
    run_count = (
        db.query(GenericScrapeRun)
        .filter(GenericScrapeRun.source_config_id == source_id)
        .count()
    )
    product_count = (
        db.query(GenericProduct)
        .filter(GenericProduct.source_config_id == source_id)
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
    db: Session = Depends(get_db),
):
    q = db.query(GenericProduct).filter(GenericProduct.sub_category_id == sub_category_id)
    if brand:
        q = q.filter(GenericProduct.brand == brand)
    if buyer_id is not None:
        q = q.filter(GenericProduct.buyer_id == buyer_id)
    return q.order_by(GenericProduct.scraped_at.desc()).all()


# ------------------------------------------------------------------ analytics
@router.get("/analytics")
def get_analytics(sub_category_id: int, buyer_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Deliberately simple: price distribution and per-brand counts only.
    No gap analysis, no AI attribute extraction, no opportunity scoring --
    there is no Suburbia-equivalent baseline to compare against for an
    arbitrary category, so this just summarizes what was found, per the
    original request for this feature.

    Price distribution is grouped BY CURRENCY (never blended across
    currencies -- same fix already applied on the Suburbia side after a
    real bug there mixed MXN and USD numbers into one meaningless
    average), uses MRP via compute_mrp() (never a discounted price), and
    does not include "median" (removed per explicit request)."""
    q = db.query(GenericProduct).filter(GenericProduct.sub_category_id == sub_category_id)
    if buyer_id is not None:
        q = q.filter(GenericProduct.buyer_id == buyer_id)
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