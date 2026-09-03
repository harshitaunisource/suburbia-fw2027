from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OpportunityStatus, ProductOpportunity
from app.schemas import (
    GenerateOpportunitiesRequest,
    OpportunityOut,
    OpportunityStatusUpdate,
    ProductOut,
)
from app.services.opportunity import compute_gap_table, generate_opportunities
from app.services.suggestions import get_suggested_products
from app.services.xlsx_export import build_opportunities_workbook

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

VALID_STATUSES = {s.value for s in OpportunityStatus}


@router.get("", response_model=list[OpportunityOut])
def list_opportunities(category: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(ProductOpportunity)
    if category:
        q = q.filter(ProductOpportunity.category == category)
    if status:
        q = q.filter(ProductOpportunity.status == status)
    return q.order_by(ProductOpportunity.opportunity_score.desc()).all()


@router.post("/generate", response_model=list[OpportunityOut])
def generate(req: GenerateOpportunitiesRequest, db: Session = Depends(get_db)):
    return generate_opportunities(
        db, category=req.category, top_n=req.top_n,
        our_source=req.our_source, competitor_sources=req.competitor_sources,
    )


@router.get("/export")
def export_opportunities(
    category: str,
    our_source: str = "suburbia",
    competitor_sources: str | None = Query(None, description="Comma-separated list, e.g. 'zara,hm'"),
    db: Session = Depends(get_db),
):
    """Downloads the current opportunities list + gap table for this
    buyer/competitor comparison as an .xlsx workbook."""
    comp_list = [s.strip() for s in competitor_sources.split(",") if s.strip()] if competitor_sources else None
    opportunities = (
        db.query(ProductOpportunity)
        .filter(ProductOpportunity.category == category)
        .order_by(ProductOpportunity.opportunity_score.desc())
        .all()
    )
    gap_table = compute_gap_table(db, category, our_source=our_source, competitor_sources=comp_list)
    content = build_opportunities_workbook(opportunities, gap_table, category, our_source, comp_list)
    filename = f"opportunities_{our_source}_{category}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.patch("/{opportunity_id}/status", response_model=OpportunityOut)
def update_status(opportunity_id: int, body: OpportunityStatusUpdate, db: Session = Depends(get_db)):
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")
    opp = db.query(ProductOpportunity).get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opp.status = body.status
    db.commit()
    db.refresh(opp)
    return opp


@router.get("/{opportunity_id}/suggested-products", response_model=list[ProductOut])
def suggested_products(opportunity_id: int, limit: int = 8, db: Session = Depends(get_db)):
    """Real, already-scraped competitor products matching this
    opportunity's concept -- pick the closest one to seed a catalogue
    entry in one click instead of typing a new product by hand."""
    opp = db.query(ProductOpportunity).get(opportunity_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return get_suggested_products(db, opp, limit=limit)