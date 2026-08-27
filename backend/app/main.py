from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import analytics, attributes, catalogue, dashboard, opportunities, products, scrapers
from app.scrapers.base import STORAGE_ROOT

app = FastAPI(title="Suburbia FW2027 Fashion Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    (STORAGE_ROOT / "catalogue").mkdir(parents=True, exist_ok=True)


app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(scrapers.router)
app.include_router(attributes.router)
app.include_router(analytics.router)
app.include_router(opportunities.router)
app.include_router(catalogue.router)

# Serves downloaded product/catalogue images directly, e.g.
# GET /storage/products/suburbia/sweaters/SB123.jpg -- so the frontend
# can display real downloaded images instead of hot-linking (and being
# blocked/rate-limited by) the original competitor sites.
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(STORAGE_ROOT)), name="storage")


@app.get("/api/health")
def health():
    return {"status": "ok"}
