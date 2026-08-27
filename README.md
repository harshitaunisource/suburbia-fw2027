# Suburbia Mexico FW2027 — Fashion Intelligence & Buyer Proposal System

Scrape market data → analyze competitors and Suburbia → identify
assortment gaps → recommend products → select final products → generate
a professional buyer-facing catalogue.

Scope: Suburbia Mexico, Women's Sweaters + Women's Blouses, vs Zara,
H&M, C&A, Primark, Target, Old Navy, SHEIN, Boohoo, ASOS.

---

## Please read this before running scrapers

This project was built and tested in an environment **with no internet
access**, so the application logic (database, AI attribute extraction,
analytics, gap analysis, opportunity scoring, catalogue PDF generation)
has been run end-to-end and verified to work correctly — but the
**scrapers themselves could not be tested against the live websites**.

Confidence level by source (see each scraper's docstring in
`backend/app/scrapers/` for details):

| Source | Confidence | Notes |
|---|---|---|
| Suburbia | High | Live-verified end to end, handles dead product links gracefully |
| Old Navy | High | Live-verified end to end |
| ASOS | Medium | Live-verified (71 real products), price extraction fixed since |
| C&A | Medium | Live-verified with real data, some fields incomplete |
| H&M | Medium | Built from real captured pages, Playwright required (Akamai WAF) |
| Zara | Medium-Low | Real Akamai bot-challenge (proof-of-work) confirmed live — may simply not be scrapeable without additional infrastructure |
| Target, SHEIN, Boohoo, Primark | Low / Unverified | Architecture-complete, defensive, but selectors are best-effort and need a first real smoke test |

**None of the scrapers fabricate data.** If a site can't be reached or
its structure doesn't match, the scraper raises a clear error and the
Data Collection page shows "failed" with the reason — it will never
silently invent products. Expect to smoke-test each source once, look
at real failures, and tighten a regex or selector — the same iterative
process already used to build Suburbia/Old Navy/ASOS.

Also note: Zara (Akamai proof-of-work challenge) and SHEIN (bot
risk-challenge redirect) are aggressively protected. This project
deliberately does not attempt to defeat those systems — if you need
their data in practice, budget for manual sampling or a licensed
retail-data feed for those two specifically.

---

## Project structure

```
backend/
  app/
    main.py                 FastAPI app, routers, static file mount
    models.py                SQLAlchemy models (products, attributes,
                              opportunities, catalogue_products, scrape_runs)
    database.py               DB session / init
    schemas.py                 Pydantic request/response models
    scrapers/                  One module per site + shared helpers
    services/
      ingest.py                 Scrape orchestration + DB upsert
      attributes.py              Phase 5: AI attribute extraction
      analytics.py                Phase 6: market analytics
      opportunity.py                Phase 7-8: gap analysis + scoring
      catalogue.py                  Phase 10: PDF generation
      ai/                           Swappable AI provider layer
    routers/                    One router per feature area
  scripts/
    seed_demo_data.py           Optional: seed realistic demo data (no scraping)
    run_pipeline.py              CLI: run the whole pipeline end to end
  storage/
    products/<source>/          Downloaded competitor/Suburbia images
    catalogue/                    Generated PDFs + uploaded "our product" photos
frontend/
  src/pages/
    Dashboard.jsx, DataCollection.jsx, Products.jsx,
    Analytics.jsx, Opportunities.jsx, OurProducts.jsx, Catalogue.jsx
```

---

## Prerequisites

- Python 3.11+ and pip
- Node.js 18+ and npm
- (Optional, for JS-heavy sites) a Chrome/Chromium browser for Playwright

---

## 1. Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate            # (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install chrome      # optional, tried first if present
copy .env.example .env                   # (macOS/Linux: cp .env.example .env)
```

By default `.env` uses a local SQLite file (`suburbia_fw2027.db`) and
`AI_PROVIDER=mock` (no API key needed) — good enough to run the entire
pipeline and see real output immediately. To use Postgres or real AI
attribute extraction, edit `.env` (see comments inside it).

Start the API:

```powershell
uvicorn app.main:app --reload --port 8001
```

Check `http://localhost:8001/api/health` → `{"status": "ok"}`.

## 2. Frontend setup

```powershell
cd frontend
npm install
npm run dev
```

Open the printed URL (usually `http://localhost:5173`).

## 3. See the whole pipeline working immediately (no scraping needed)

Before touching real scrapers, seed realistic demo data and run the
whole downstream pipeline against it — this is exactly what was used to
verify this build:

```powershell
cd backend
python -m scripts.seed_demo_data
python -m scripts.run_pipeline --skip-scrape
```

Now open the frontend: Dashboard, Products, Market Analytics, Suburbia
Opportunities will all show real (demo) data, and you can add an "Our
Product" entry, approve it, and generate a real catalogue PDF from
**Generate Catalogue**.

Delete `backend/suburbia_fw2027.db` afterward to start clean before
running real scrapers.

## 4. Run real scrapers

Either from the UI (**Data Collection** page → "Run Scraper" per row —
rows marked ● have an unverified category URL, confirm it in a browser
first), or from the CLI:

```powershell
cd backend
python -m scripts.run_pipeline --sources suburbia,old_navy --categories sweaters,blouses
```

Run one source at a time the first time, read any error message, and
fix the relevant scraper's selectors/regex against the real page before
moving to the next source — do not expect all 10 sources x 2 categories
to work perfectly on the very first run against sites this defended.

Then run the rest of the pipeline for real data:

```powershell
python -m scripts.run_pipeline --skip-scrape
```

(or trigger each phase from the UI: AI attribute extraction is
triggered automatically as part of `run_pipeline`; from the UI it's not
yet exposed as a button — call `POST /api/attributes/run` directly, or
add a button, if you want it in-app.)

## 5. End-to-end workflow in the UI

1. **Data Collection** — run scrapers for Suburbia + competitors.
2. **Products** — browse everything scraped, filter by source/category.
3. `POST /api/attributes/run` (curl/Postman, or via `run_pipeline.py`) —
   runs AI attribute extraction.
4. **Market Analytics** — price distribution, color/pattern/silhouette/
   neckline breakdowns, filterable by category/source group.
5. **Suburbia Opportunities** — click "Generate / Refresh Opportunities"
   per category, review the gap table + scored concepts, Shortlist or
   Reject each one.
6. **Our Products** — add your own product entries (name, code, fabric,
   price, MOQ, lead time, etc.) and upload your own product/sample/
   concept photos (never competitor images — the system won't allow it).
7. **Generate Catalogue** — approve products in Our Products, then
   generate and download the buyer-facing PDF. The PDF never contains
   competitor prices/URLs, internal scores, or analytics — only your
   approved products and images (enforced in code, not just by policy).

## Switching to real AI attribute extraction

```
# in backend/.env
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

```powershell
pip install anthropic
```

## Switching to Postgres

```
# in backend/.env
DATABASE_URL=postgresql+psycopg2://suburbia:suburbia@localhost:5432/suburbia_fw2027
```

Create the database first (`createdb suburbia_fw2027`); tables are
created automatically on API startup.
