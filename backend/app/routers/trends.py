"""
Trend Matching feature: upload a buyer trend deck (.pptx/.pdf, mostly
images with little/no text), get every embedded image AI-classified
into a short product description, then for each trend product find
candidate matches both in your own already-scraped competitor data
(Asos/C&A/Primark/etc, the same `products` table the Products page
reads from) and on the open web (image search) -- review and
multi-select real matches, which feed into the EXACT SAME cart/PPT
pipeline every other page in this app already uses (see
routers/catalogue.py), rather than a separate export path.

CLASSIFICATION RUNS AS A BACKGROUND TASK, NOT INLINE IN THE UPLOAD
REQUEST. Confirmed live failure this fixes: uploading a deck with 200+
images kept the request's one database connection open but completely
idle through the whole (potentially many-minute) classification loop,
then tried one big commit at the end -- Neon Postgres dropped that
idle connection ("SSL connection has been closed unexpectedly") before
the commit could complete, and the resulting 500 (HTML/plain error
page, not JSON) crashed the frontend's `res.json()` call with
"Unexpected token 'I', 'Internal S'... is not valid JSON".

The fix mirrors services/generic_scraper.py's identical pattern
(established there for the same underlying reason -- see that file's
docstring): the upload endpoint saves the raw extracted images fast and
returns immediately; a BackgroundTask then classifies images ONE AT A
TIME with its OWN database session, committing after every single image
(see _commit_with_retry below) so no one transaction is ever open long
enough to go idle, and updating TrendUpload.products_classified as it
goes so the frontend can poll GET /api/trends/{id} for real progress
instead of one static "please wait."
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import (
    CatalogueProduct,
    ImageKind,
    Product,
    TrendMatch,
    TrendMatchSourceType,
    TrendProduct,
    TrendUpload,
)
from app.schemas import TrendMatchOut, TrendProductOut, TrendProductWithMatchesOut, TrendUploadOut
from app.scrapers.base import STORAGE_ROOT
from app.services.deck_extract import DeckExtractError, ExtractedImage, extract_images
from app.services.image_search.base import ImageSearchError
from app.services.image_search.factory import get_image_search_provider
from app.services.trend_matching import find_catalogue_matches
from app.services.vision_classify import classify_product_image

router = APIRouter(prefix="/api/trends", tags=["trends"])

TREND_IMAGE_DIR = STORAGE_ROOT / "trend_matching" / "trend"
_CONTENT_TYPE_TO_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/bmp": ".bmp", "image/webp": ".webp"}


def _save_extracted_image(image_bytes: bytes, content_type: str, prefix: str, index: int) -> str:
    TREND_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    ext = _CONTENT_TYPE_TO_EXT.get(content_type, ".png")
    safe_name = hashlib.md5(f"{prefix}-{index}".encode()).hexdigest()[:16]
    target_path = TREND_IMAGE_DIR / f"{safe_name}{ext}"
    with open(target_path, "wb") as f:
        f.write(image_bytes)
    return str(target_path.relative_to(STORAGE_ROOT.parent).as_posix())


def _commit_with_retry(db: Session, max_attempts: int = 2):
    """Commits the current transaction, retrying once with a rollback in
    between on a transient OperationalError (e.g. a dropped Postgres
    connection) -- pool_pre_ping (see database.py) only re-validates a
    connection when it's freshly checked OUT of the pool, which doesn't
    help here since this background task holds one session/connection
    for its whole run. A rollback + retry gives the pool a chance to
    hand back a working connection on the next attempt instead of the
    whole classification run dying on one blip."""
    for attempt in range(max_attempts):
        try:
            db.commit()
            return
        except OperationalError:
            db.rollback()
            if attempt == max_attempts - 1:
                raise


def classify_trend_upload_background(upload_id: int, extracted: list[ExtractedImage]) -> None:
    """BackgroundTasks entry point -- opens its OWN database session (the
    request-scoped session from the endpoint that scheduled this is
    closed as soon as the HTTP response is sent, long before this
    function actually runs). See this file's module docstring for why
    classification happens here instead of inline in the upload
    request."""
    db = SessionLocal()
    try:
        upload = db.get(TrendUpload, upload_id)
        if not upload:
            return

        classified = 0
        for i, img in enumerate(extracted):
            try:
                rel_path = _save_extracted_image(img.image_bytes, img.content_type, f"trend-{upload_id}", i)
                classification = classify_product_image(img.image_bytes, img.content_type)
                db.add(TrendProduct(
                    upload_id=upload_id,
                    image_path=rel_path,
                    slide_number=img.slide_number,
                    ai_name=classification.name,
                    ai_category=classification.category,
                    ai_color=classification.color,
                    ai_pattern=classification.pattern,
                    ai_description=classification.description,
                    ai_confidence=classification.confidence,
                ))
                classified += 1
                upload.products_classified = classified
                _commit_with_retry(db)
            except Exception:
                # One bad image (a corrupt embed, a classification API
                # hiccup) should not abort the rest of a large deck --
                # skip it and keep going. Rollback first: if this
                # iteration's failure happened mid-transaction, the
                # session needs to be clean before the next iteration's
                # db.add() below.
                db.rollback()
                continue

        upload.status = "ready"
        _commit_with_retry(db)
    finally:
        db.close()


@router.post("/upload", response_model=TrendUploadOut)
async def upload_trend_deck(
    file: UploadFile = File(...),
    buyer_label: str = Form(None),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    file_bytes = await file.read()
    upload = TrendUpload(filename=file.filename, buyer_label=buyer_label, status="processing")
    db.add(upload)
    db.commit()
    db.refresh(upload)

    try:
        images = extract_images(file.filename, file_bytes)
    except DeckExtractError as e:
        upload.status = "failed"
        upload.error_message = str(e)
        db.commit()
        db.refresh(upload)
        return upload

    if not images:
        upload.status = "failed"
        upload.error_message = (
            "No product-sized images found in this file -- confirm it's the right deck "
            "and that images are actually embedded (not just linked/referenced)."
        )
        db.commit()
        db.refresh(upload)
        return upload

    upload.total_products = len(images)
    db.commit()
    db.refresh(upload)

    background_tasks.add_task(classify_trend_upload_background, upload.id, images)
    return upload


@router.get("", response_model=list[TrendUploadOut])
def list_trend_uploads(db: Session = Depends(get_db)):
    return db.query(TrendUpload).order_by(TrendUpload.created_at.desc()).all()


# --------------------------------------------------------------- selection
# Registered before "/{upload_id}" below on purpose -- see the ordering
# note further down (a confirmed, previously-hit bug in this exact file).

@router.post("/matches/{match_id}/select")
def select_match(match_id: int, db: Session = Depends(get_db)):
    """Toggles whether a suggested match is in the current PPT batch --
    reuses the exact same CatalogueProduct/source_ref cart mechanism as
    the "Add to PPT" checkboxes on Products/Search Products/Explore
    Categories (see routers/catalogue.py), just keyed by
    source_ref=f"trend_match:{match_id}" instead of a product id. This is
    what lets Our Products, the download link, and PPT generation work
    for Trend Matching selections with zero new export code."""
    match = db.query(TrendMatch).get(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    source_ref = f"trend_match:{match.id}"
    existing = db.query(CatalogueProduct).filter(CatalogueProduct.source_ref == source_ref).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"in_cart": False, "source_ref": source_ref}

    trend_product = db.query(TrendProduct).get(match.trend_product_id)
    notes = f"Matched to buyer trend product: {trend_product.ai_name}" if trend_product else None

    if match.source_type == TrendMatchSourceType.CATALOGUE:
        product = db.query(Product).get(match.catalogue_product_id)
        if not product:
            raise HTTPException(status_code=404, detail="The catalogue product behind this match no longer exists")
        catalogue_product = CatalogueProduct(
            product_name=product.product_name,
            category=product.category,
            description=product.description,
            # Prefer the remote image_url over a locally-downloaded copy
            # -- see cartItemFromProduct in lib/cart.js for why (a local
            # file only exists on whichever machine ran that scrape).
            image_path=product.image_url or product.local_image_path,
            image_kind=ImageKind.COMPETITOR,
            colorways=product.colors,
            fabric=product.material,
            notes=(notes or "") + f" Source: {product.source} ({product.product_url})",
            source_ref=source_ref,
            approved=True,
        )
    else:
        catalogue_product = CatalogueProduct(
            product_name=match.web_title or "Web match",
            category=trend_product.ai_category if trend_product else None,
            description=None,
            image_path=match.web_image_url,
            image_kind=ImageKind.COMPETITOR,
            colorways=None,
            fabric=None,
            notes=(notes or "") + (f" Source: {match.web_source_url}" if match.web_source_url else ""),
            source_ref=source_ref,
            approved=True,
        )

    db.add(catalogue_product)
    db.commit()
    db.refresh(catalogue_product)
    return {"in_cart": True, "source_ref": source_ref}


# ------------------------------------------------------- per-upload routes
# NOTE: parameterized routes go LAST in this file. FastAPI/Starlette
# matches routes in registration order, and a route like
# "/{upload_id}/products" has the same shape (two path segments) as any
# literal two-segment route registered after it -- confirmed live: this
# exact ordering mistake previously made "/vendor-catalogue/products"
# get swallowed by "/{upload_id}/products" registered before it. There's
# no other literal-prefixed route left in this file after removing the
# vendor catalogue feature, but keeping this convention (literal routes
# first, parameterized last) avoids ever having to re-reason about this
# file's order again when a new endpoint gets added later.

@router.get("/{upload_id}", response_model=TrendUploadOut)
def get_trend_upload(upload_id: int, db: Session = Depends(get_db)):
    """Polled by the frontend every couple of seconds while status is
    'processing' to show live "X / Y classified" progress -- see this
    file's module docstring for why classification isn't synchronous."""
    upload = db.query(TrendUpload).get(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Trend upload not found")
    return upload


@router.get("/{upload_id}/products", response_model=list[TrendProductOut])
def list_trend_products(upload_id: int, db: Session = Depends(get_db)):
    return db.query(TrendProduct).filter(TrendProduct.upload_id == upload_id).order_by(TrendProduct.id).all()


@router.post("/{upload_id}/match")
def run_matching(upload_id: int, web_results_per_product: int = 4, db: Session = Depends(get_db)):
    upload = db.query(TrendUpload).get(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Trend upload not found")
    if upload.status != "ready":
        raise HTTPException(status_code=400, detail="This trend upload hasn't finished classifying yet")

    trend_products = db.query(TrendProduct).filter(TrendProduct.upload_id == upload_id).all()
    if not trend_products:
        raise HTTPException(status_code=400, detail="This trend upload has no classified products yet")

    try:
        image_search = get_image_search_provider()
    except ImageSearchError as e:
        raise HTTPException(status_code=400, detail=str(e))

    total_matches = 0
    web_errors = 0
    for trend_product in trend_products:
        # Re-running matching for an upload should reflect fresh results,
        # not pile duplicates on top of a previous run.
        db.query(TrendMatch).filter(TrendMatch.trend_product_id == trend_product.id).delete()

        for product, score in find_catalogue_matches(db, trend_product):
            db.add(TrendMatch(
                trend_product_id=trend_product.id,
                source_type=TrendMatchSourceType.CATALOGUE,
                catalogue_product_id=product.id,
                score=score,
            ))
            total_matches += 1

        query = trend_product.ai_name or trend_product.ai_description
        if query:
            try:
                hits = image_search.search(query, max_results=web_results_per_product)
                for hit in hits:
                    db.add(TrendMatch(
                        trend_product_id=trend_product.id,
                        source_type=TrendMatchSourceType.WEB,
                        web_image_url=hit.image_url,
                        web_title=hit.title,
                        web_source_url=hit.source_url,
                        score=None,
                    ))
                    total_matches += 1
            except ImageSearchError:
                # One bad web search shouldn't abort matching for every
                # other trend product in this upload -- the catalogue
                # matches for this product are still saved either way.
                web_errors += 1

    db.commit()
    return {"trend_products": len(trend_products), "matches_created": total_matches, "web_search_errors": web_errors}


@router.get("/{upload_id}/matches", response_model=list[TrendProductWithMatchesOut])
def get_matches(upload_id: int, db: Session = Depends(get_db)):
    trend_products = db.query(TrendProduct).filter(TrendProduct.upload_id == upload_id).order_by(TrendProduct.id).all()

    result = []
    for tp in trend_products:
        matches = db.query(TrendMatch).filter(TrendMatch.trend_product_id == tp.id).order_by(TrendMatch.score.desc().nullslast()).all()
        match_outs = []
        for m in matches:
            display_image_url, display_name, display_source_url = None, None, None
            if m.source_type == TrendMatchSourceType.CATALOGUE and m.catalogue_product_id:
                product = db.query(Product).get(m.catalogue_product_id)
                if product:
                    # Prefer the remote image_url over a local path --
                    # see Products.jsx's imageSrc for the full reasoning.
                    if product.image_url:
                        display_image_url = product.image_url
                    elif product.local_image_path:
                        normalized = product.local_image_path.replace("\\", "/")
                        idx = normalized.find("storage/")
                        display_image_url = "/" + (normalized[idx:] if idx >= 0 else normalized)
                    display_name = f"{product.product_name} ({product.source})"
                    display_source_url = product.product_url
            elif m.source_type == TrendMatchSourceType.WEB:
                display_image_url = m.web_image_url
                display_name = m.web_title
                display_source_url = m.web_source_url
            out = TrendMatchOut.model_validate(m)
            out.display_image_url = display_image_url
            out.display_name = display_name
            out.display_source_url = display_source_url
            match_outs.append(out)
        result.append(TrendProductWithMatchesOut(product=TrendProductOut.model_validate(tp), matches=match_outs))
    return result