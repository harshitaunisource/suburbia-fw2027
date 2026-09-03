from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import RunAttributeExtractionRequest
from app.services.attributes import run_attribute_extraction

router = APIRouter(prefix="/api/attributes", tags=["attributes"])


@router.post("/run")
def run_extraction(req: RunAttributeExtractionRequest, db: Session = Depends(get_db)):
    return run_attribute_extraction(db, limit=req.limit, category=req.category, force=req.force)