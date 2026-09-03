"""
Phase 9 + 10 endpoints: Our Product management (spec section 15) and
Buyer Catalogue generation (spec section 16).
"""
import hashlib
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CatalogueProduct, ImageKind, Product, ProductOpportunity, OpportunityStatus
from app.services.pricing import compute_mrp
from app.schemas import (
    CartToggleRequest,
    CatalogueProductFromProductRequest,
    CatalogueProductIn,
    CatalogueProductOut,
    GenerateCatalogueRequest,
)
from app.scrapers.base import STORAGE_ROOT
from app.services.catalogue import generate_catalogue_pptx

router = APIRouter(prefix="/api/catalogue", tags=["catalogue"])

OUR_PRODUCTS_DIR = STORAGE_ROOT / "catalogue" / "our_products"
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@router.get("/products", response_model=list[CatalogueProductOut])
def list_catalogue_products(approved: bool | None = None, db: Session = Depends(get_db)):
    q = db.query(CatalogueProduct)
    if approved is not None:
        q = q.filter(CatalogueProduct.approved.is_(approved))
    return q.order_by(CatalogueProduct.sort_order, CatalogueProduct.id).all()


# ------------------------------------------------------------------ cart
# "Cart" is not a separate table -- it's simply every CatalogueProduct
# row that has a source_ref. Storing it as real rows (instead of, say,
# frontend-only state) means the selection survives navigating between
# pages AND a full page refresh, without any extra plumbing: the
# Products / Search Products / Explore Categories pages just ask
# GET /cart/refs once on load to know which checkboxes should start
# checked.
@router.get("/cart/refs")
def list_cart_refs(db: Session = Depends(get_db)):
    """Every source_ref currently in the cart -- e.g.
    ["product:12", "generic_product:44"]. Used to restore checkbox state
    when a product-listing page loads."""
    rows = (
        db.query(CatalogueProduct.source_ref)
        .filter(CatalogueProduct.source_ref.isnot(None))
        .all()
    )
    return [r[0] for r in rows]


@router.post("/cart/toggle", response_model=CatalogueProductOut | dict)
def toggle_cart_item(body: CartToggleRequest, db: Session = Depends(get_db)):
    """Checking a product's 'Add to PPT' box calls this; unchecking it
    calls this again with the same source_ref. Whichever state it's NOT
    currently in is the one it moves to."""
    existing = (
        db.query(CatalogueProduct)
        .filter(CatalogueProduct.source_ref == body.source_ref)
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()
        return {"in_cart": False, "source_ref": body.source_ref}

    product = CatalogueProduct(
        product_name=body.product_name,
        category=body.category,
        description=body.description,
        image_path=body.image_path,
        image_kind=ImageKind.COMPETITOR if body.image_path else ImageKind.OUR_PRODUCT,
        colorways=body.colorways,
        fabric=body.fabric,
        size_range=body.size_range,
        target_price=body.target_price,
        currency=body.currency or "USD",
        notes=body.notes,
        source_ref=body.source_ref,
        approved=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/cart")
def clear_cart(db: Session = Depends(get_db)):
    """Manual 'Clear Cart' button -- removes every current cart item
    (source_ref IS NOT NULL) without waiting for a PPT to be generated.
    Does not touch any older, non-cart catalogue rows (source_ref IS
    NULL) that may still exist from before this feature."""
    deleted = (
        db.query(CatalogueProduct)
        .filter(CatalogueProduct.source_ref.isnot(None))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


@router.post("/products", response_model=CatalogueProductOut)
def create_catalogue_product(body: CatalogueProductIn, db: Session = Depends(get_db)):
    product = CatalogueProduct(**body.model_dump(), image_kind=ImageKind.OUR_PRODUCT)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/products/{product_id}", response_model=CatalogueProductOut)
def update_catalogue_product(product_id: int, body: CatalogueProductIn, db: Session = Depends(get_db)):
    product = db.query(CatalogueProduct).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Catalogue product not found")
    for k, v in body.model_dump().items():
        setattr(product, k, v)
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/{product_id}/approve", response_model=CatalogueProductOut)
def approve_catalogue_product(product_id: int, approved: bool = True, db: Session = Depends(get_db)):
    product = db.query(CatalogueProduct).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Catalogue product not found")
    product.approved = approved
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}")
def delete_catalogue_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(CatalogueProduct).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Catalogue product not found")
    db.delete(product)
    db.commit()
    return {"deleted": True}


@router.post("/products/{product_id}/image", response_model=CatalogueProductOut)
def upload_catalogue_image(
    product_id: int,
    file: UploadFile = File(...),
    kind: str = "OUR_PRODUCT",
    db: Session = Depends(get_db),
):
    """Uploads OUR own product photo / approved sample photo / concept
    image for a catalogue entry. Explicitly tagged with an ImageKind so
    the catalogue generator's provenance check (spec section 3/18) can
    enforce that competitor imagery never ends up here."""
    product = db.query(CatalogueProduct).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Catalogue product not found")

    if kind not in ("OUR_PRODUCT", "CONCEPT"):
        raise HTTPException(status_code=400, detail="kind must be OUR_PRODUCT or CONCEPT")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported image type '{ext}'")

    OUR_PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = hashlib.md5(f"{product_id}-{file.filename}".encode()).hexdigest()[:16]
    target_path = OUR_PRODUCTS_DIR / f"{safe_name}{ext}"
    with open(target_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    product.image_path = str(target_path.relative_to(STORAGE_ROOT.parent))
    product.image_kind = ImageKind.OUR_PRODUCT if kind == "OUR_PRODUCT" else ImageKind.CONCEPT
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/from-product", response_model=CatalogueProductOut)
def create_catalogue_product_from_competitor(
    body: CatalogueProductFromProductRequest, db: Session = Depends(get_db)
):
    """The fast-path workflow: pick the closest-matching already-scraped
    competitor product for a shortlisted opportunity, and seed a
    catalogue entry from it in one click (name, description, colors,
    price, and image all copied over) instead of typing a new product by
    hand. The copied image is explicitly kept tagged COMPETITOR_IMAGE --
    see app/services/catalogue.py for how that's surfaced, clearly
    labeled, in the generated deck rather than silently presented as an
    original Suburbia photo."""
    opportunity = db.query(ProductOpportunity).get(body.opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    source_product = db.query(Product).get(body.product_id)
    if not source_product:
        raise HTTPException(status_code=404, detail="Source product not found")

    # MRP-only rule (2026-08-31): use the shared compute_mrp() helper
    # (app/services/pricing.py) -- the single sanctioned way to derive a
    # usable price anywhere in this project, never a discounted/sale
    # price.
    mrp = compute_mrp(source_product.price, source_product.original_price)

    catalogue_product = CatalogueProduct(
        opportunity_id=opportunity.id,
        product_name=source_product.product_name,
        our_product_code=None,
        category=source_product.category,
        description=source_product.description,
        image_path=source_product.local_image_path,
        image_kind=ImageKind.COMPETITOR if source_product.local_image_path else ImageKind.OUR_PRODUCT,
        colorways=source_product.colors,
        fabric=source_product.material,
        size_range=source_product.sizes,
        target_price=mrp,
        # Fixes a real, confirmed-live bug: this field did not exist on
        # CatalogueProduct at all before, so a competitor's price in any
        # non-USD currency (confirmed on Zara, priced in INR) got its
        # currency information silently dropped here, and the generated
        # PPT then displayed it with a hardcoded "$" regardless of the
        # real currency. Always carry the source product's actual
        # currency through explicitly.
        currency=source_product.currency or "USD",
        notes=(
            f"Reference product from {source_product.source}"
            + (f" ({source_product.brand})" if source_product.brand else "")
            + f". Original: {source_product.product_url}"
        ),
        approved=True,  # fast workflow: shortlist -> pick reference -> straight into the deck
    )
    db.add(catalogue_product)

    # Marks the opportunity as actioned so it's clear at a glance which
    # shortlisted concepts already have a catalogue entry.
    opportunity.status = OpportunityStatus.selected
    db.commit()
    db.refresh(catalogue_product)
    return catalogue_product


@router.post("/generate")
def generate_catalogue(req: GenerateCatalogueRequest, db: Session = Depends(get_db)):
    path = generate_catalogue_pptx(
        db,
        collection_title=req.collection_title,
        season_title=req.season_title,
        market_direction=req.market_direction,
    )
    cleared = 0
    if req.clear_after:
        # The batch that just went into this deck is done with -- clear
        # it so the merchant can start selecting a fresh set of products
        # for the next PPT immediately, instead of having to delete each
        # entry from the last batch by hand first.
        cleared = (
            db.query(CatalogueProduct)
            .filter(CatalogueProduct.source_ref.isnot(None))
            .delete(synchronize_session=False)
        )
        db.commit()
    return {"path": path, "filename": os.path.basename(path), "cleared": cleared}


@router.get("/download/{filename}")
def download_catalogue(filename: str):
    from app.services.catalogue import OUTPUT_DIR

    safe_name = os.path.basename(filename)  # prevent path traversal
    path = OUTPUT_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Catalogue file not found")
    media_type = (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if safe_name.endswith(".pptx")
        else "application/pdf"
    )
    return FileResponse(str(path), media_type=media_type, filename=safe_name)