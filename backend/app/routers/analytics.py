from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import analytics as analytics_service
from app.services.opportunity import compute_gap_table
from app.services.xlsx_export import build_analytics_workbook

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _parse_sources(sources: str | None) -> list[str] | None:
    return [s.strip() for s in sources.split(",") if s.strip()] if sources else None


@router.get("")
def get_analytics(
    category: str | None = None,
    brand: str | None = None,
    group: str | None = Query(None, description="'suburbia' or 'competitors' (ignored if sources is given)"),
    sources: str | None = Query(None, description="Comma-separated list of Product.source values, e.g. 'suburbia,zara,hm'"),
    db: Session = Depends(get_db),
):
    return analytics_service.full_report(
        db, category=category, brand=brand, group=group, sources=_parse_sources(sources)
    )


@router.get("/export")
def export_analytics(
    category: str | None = None,
    sources: str | None = Query(None, description="Comma-separated list of Product.source values"),
    db: Session = Depends(get_db),
):
    """Downloads the exact same data the Market Analytics page shows,
    as an .xlsx workbook -- one sheet per chart."""
    source_list = _parse_sources(sources)
    report = analytics_service.full_report(db, category=category, sources=source_list)
    content = build_analytics_workbook(report, category, source_list)
    filename = f"market_analytics_{category or 'all'}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/gap")
def get_gap_table(
    category: str,
    our_source: str = "suburbia",
    competitor_sources: str | None = Query(None, description="Comma-separated list, e.g. 'women_secret'"),
    db: Session = Depends(get_db),
):
    comp_list = competitor_sources.split(",") if competitor_sources else None
    return compute_gap_table(db, category, our_source=our_source, competitor_sources=comp_list)