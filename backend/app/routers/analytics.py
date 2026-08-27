from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import analytics as analytics_service
from app.services.opportunity import compute_gap_table

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("")
def get_analytics(
    category: str | None = None,
    brand: str | None = None,
    group: str | None = Query(None, description="'suburbia' or 'competitors'"),
    db: Session = Depends(get_db),
):
    return analytics_service.full_report(db, category=category, brand=brand, group=group)


@router.get("/gap")
def get_gap_table(category: str, db: Session = Depends(get_db)):
    return compute_gap_table(db, category)
