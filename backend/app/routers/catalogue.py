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
from app.schemas import (
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
        target_price=source_product.price,
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
    return {"path": path, "filename": os.path.basename(path)}


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