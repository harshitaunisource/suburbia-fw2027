"""
End-to-end CLI pipeline runner: scrape (all sources x both categories) ->
AI attribute extraction -> opportunity generation, for both categories.

Every step is wrapped so one source/category failing never stops the
rest -- you'll get a clear per-source summary at the end showing exactly
what succeeded, what failed, and why (spec section 7: report failures,
never fabricate data).

Usage:
    cd backend && python -m scripts.run_pipeline
    cd backend && python -m scripts.run_pipeline --sources suburbia,old_navy --categories sweaters
"""
import argparse

from app.database import SessionLocal, init_db
from app.scrapers.registry import SCRAPERS
from app.services.attributes import run_attribute_extraction
from app.services.ingest import run_scrape
from app.services.opportunity import generate_opportunities

# Keep in sync with frontend/src/pages/DataCollection.jsx
# All URLs below are real, user-confirmed working category pages
# (2026-08-26) -- see each scraper's module docstring for locale/
# currency notes specific to that source.
CATEGORY_URLS = {
    "suburbia": {
        "sweaters": "https://www.suburbia.com.mx/tienda/su%C3%A9teres/cat_SB_3008",
        "blouses": "https://www.suburbia.com.mx/tienda/blusas/cat_SB_3001",
    },
    "zara": {
        "sweaters": "https://www.zara.com/in/en/woman-knitwear-l1152.html",
        "blouses": "https://www.zara.com/in/en/woman-shirts-blouses-l1221.html",
    },
    "hm": {
        "sweaters": "https://www2.hm.com/en_in/women/shop-by-product/cardigans-jumpers/jumpers.html",
        "blouses": "https://www2.hm.com/en_in/women/shop-by-product/shirts-blouses.html",
    },
    "c_and_a": {
        "sweaters": "https://www.cyamoda.com/mujer/ropa/sueteres/",
        "blouses": "https://www.cyamoda.com/mujer/ropa/blusas/",
    },
    "primark": {
        "sweaters": "https://www.primark.com/en-us/c/women/clothing/sweaters-and-cardigans",
        "blouses": "https://www.primark.com/en-gb/c/women/clothing/shirts-and-blouses/blouses",
    },
    "target": {
        "sweaters": "https://www.target.com/c/sweaters-women-s-clothing/-/N-5xtbx",
        "blouses": "https://www.target.com/c/shirts-blouses-women-s-clothing/-/N-m7sh2",
    },
    "old_navy": {
        "sweaters": "https://oldnavy.gap.com/browse/women/sweaters-and-cardigans?cid=20408#department=136",
        "blouses": "https://oldnavy.gap.com/shop/womens-fashion-blouses-0aaz22b",
    },
    "shein": {
        "sweaters": "https://www.shein.com.mx/category/Sweaters-sc-00831455.html",
        "blouses": "https://www.shein.com.mx/style/Women-Blouses-sc-00122967.html",
    },
    "boohoo": {
        "sweaters": "https://us.boohoo.com/categories/womens-knitwear-jumpers",
        "blouses": "https://www.boohoo.com/categories/womens-tops-shirts-and-blouses",
    },
    "asos": {
        "sweaters": "https://www.asos.com/us/women/jumpers-cardigans/cat/?cid=2637",
        "blouses": "https://www.asos.com/us/women/shirts-blouses/cat/?cid=15200",
    },
}


def main():
    parser = argparse.ArgumentParser(description="Run the full Suburbia FW2027 pipeline")
    parser.add_argument("--sources", default=",".join(SCRAPERS.keys()))
    parser.add_argument("--categories", default="sweaters,blouses")
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--skip-scrape", action="store_true", help="Skip scraping, just run AI + opportunities")
    parser.add_argument(
        "--scrape-only", action="store_true",
        help="Only scrape -- skip AI attribute extraction and opportunity scoring. "
             "Use this while going source-by-source; run once more at the end "
             "with --skip-scrape to process everything you've collected.",
    )
    args = parser.parse_args()

    if args.skip_scrape and args.scrape_only:
        raise SystemExit("--skip-scrape and --scrape-only are mutually exclusive.")

    sources = args.sources.split(",")
    categories = args.categories.split(",")

    init_db()
    db = SessionLocal()
    summary = []

    if not args.skip_scrape:
        print("=" * 70)
        print("PHASE 1-4: SCRAPING + IMAGE DOWNLOAD")
        print("=" * 70)
        for source in sources:
            for category in categories:
                url = CATEGORY_URLS.get(source, {}).get(category)
                if not url:
                    print(f"[skip] no category URL configured for {source}/{category}")
                    continue
                print(f"\n--- {source} / {category} ---")
                try:
                    run = run_scrape(db, source, category, url, max_pages=args.max_pages)
                    print(f"  status={run.status}  found={run.products_found}  "
                          f"new={run.products_new}  images_ok={run.images_downloaded}  "
                          f"images_failed={run.images_failed}")
                    if run.error_message:
                        print(f"  error: {run.error_message}")
                    summary.append((source, category, run.status, run.products_found))
                except Exception as e:
                    print(f"  CRASHED (unexpected, not a normal ScraperError): {e}")
                    summary.append((source, category, "crashed", 0))
                    # A dropped/broken database connection (e.g. Neon's
                    # free-tier pooler closing an idle connection mid-run
                    # -- confirmed live during a long image-download
                    # loop) leaves this Session in a permanently broken
                    # state; every query on it afterwards fails too,
                    # cascading a single transient blip into every
                    # remaining source/category failing for the rest of
                    # this run. Rolling back and swapping in a fresh
                    # Session bounds the damage to just this one
                    # iteration instead.
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    db.close()
                    db = SessionLocal()

    print("\n" + "=" * 70)
    print("PHASE 5: AI ATTRIBUTE EXTRACTION")
    print("=" * 70)
    if not args.scrape_only:
        for category in categories:
            result = run_attribute_extraction(db, limit=5000, category=category)
            print(f"  {category}: {result}")
    else:
        print("  (skipped -- --scrape-only was set)")

    print("\n" + "=" * 70)
    print("PHASES 6-8: ANALYTICS + GAP ANALYSIS + OPPORTUNITY SCORING")
    print("=" * 70)
    if not args.scrape_only:
        for category in categories:
            opps = generate_opportunities(db, category, top_n=15)
            print(f"  {category}: generated {len(opps)} opportunities")
            for o in opps[:5]:
                print(f"    {o.concept_name}: {o.opportunity_score}")
    else:
        print("  (skipped -- --scrape-only was set)")

    db.close()

    print("\n" + "=" * 70)
    print("SCRAPE SUMMARY")
    print("=" * 70)
    for source, category, status, found in summary:
        mark = "✓" if status == "success" else "✗"
        print(f"  {mark} {source:12s} {category:10s} status={status:10s} products={found}")

    print(
        "\nNext: open the frontend (Products / Market Analytics / Suburbia "
        "Opportunities / Our Products / Generate Catalogue) to review and "
        "act on this data."
    )


if __name__ == "__main__":
    main()