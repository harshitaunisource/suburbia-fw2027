from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CatalogueProduct, Product, ProductAttributes, ProductOpportunity, OpportunityStatus
from app.schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def stats(db: Session = Depends(get_db)):
    products_analysed = db.query(func.count(Product.id)).scalar() or 0
    images_collected = (
        db.query(func.count(Product.id)).filter(Product.local_image_path.isnot(None)).scalar() or 0
    )
    ai_classified = db.query(func.count(ProductAttributes.id)).scalar() or 0
    opportunities = db.query(func.count(ProductOpportunity.id)).scalar() or 0
    shortlisted = (
        db.query(func.count(ProductOpportunity.id))
        .filter(ProductOpportunity.status == OpportunityStatus.shortlisted)
        .scalar()
        or 0
    )
    catalogue_styles = db.query(func.count(CatalogueProduct.id)).scalar() or 0

    return DashboardStats(
        products_analysed=products_analysed,
        images_collected=images_collected,
        ai_classified=ai_classified,
        opportunities=opportunities,
        shortlisted_styles=shortlisted,
        catalogue_styles=catalogue_styles,
    )
