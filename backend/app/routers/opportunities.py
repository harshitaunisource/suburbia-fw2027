from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OpportunityStatus, ProductOpportunity
from app.schemas import (
    GenerateOpportunitiesRequest,
    OpportunityOut,
    OpportunityStatusUpdate,
    ProductOut,
)
from app.services.opportunity import generate_opportunities
from app.services.suggestions import get_suggested_products

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
    return generate_opportunities(db, category=req.category, top_n=req.top_n)


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