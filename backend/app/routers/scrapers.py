from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, ScrapeRun
from app.schemas import RunScrapeRequest, ScrapeRunOut
from app.services.ingest import run_scrape

router = APIRouter(prefix="/api/scrapers", tags=["scrapers"])


@router.get("/status")
def scraper_status(db: Session = Depends(get_db)):
    """Powers the 'Data Collection' table: source / category / products / last run / status."""
    rows = (
        db.query(
            Product.source,
            Product.category,
            func.count(Product.id).label("products"),
        )
        .group_by(Product.source, Product.category)
        .all()
    )

    latest_runs = {
        (r.source, r.category): r
        for r in db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc()).all()
    }

    result = []
    for source, category, count in rows:
        run = latest_runs.get((source, category))
        result.append(
            {
                "source": source,
                "category": category,
                "products": count,
                "last_run": run.started_at if run else None,
                "status": run.status if run else "never_run",
            }
        )
    return result


@router.post("/run", response_model=ScrapeRunOut)
def trigger_scrape(req: RunScrapeRequest, db: Session = Depends(get_db)):
    try:
        run = run_scrape(db, req.source, req.category, req.category_url, req.max_pages)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return run


@router.get("/runs", response_model=list[ScrapeRunOut])
def list_runs(source: str | None = None, db: Session = Depends(get_db)):
    q = db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc())
    if source:
        q = q.filter(ScrapeRun.source == source)
    return q.limit(50).all()
