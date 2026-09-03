"""
Directly generates opportunities for a specific buyer-vs-competitor
comparison (e.g. Textilon vs Women'Secret), bypassing the frontend
entirely -- useful when you want results immediately or the frontend
hasn't picked up the latest Opportunities.jsx yet.

Usage:
    cd backend
    python -m scripts.generate_comparison --category pajamas --our-source textilon --competitors women_secret
"""
import argparse

from app.database import SessionLocal, init_db
from app.services.opportunity import generate_opportunities


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", required=True)
    parser.add_argument("--our-source", required=True)
    parser.add_argument("--competitors", required=True, help="Comma-separated, e.g. women_secret,lupo")
    parser.add_argument("--top-n", type=int, default=15)
    args = parser.parse_args()

    competitor_sources = args.competitors.split(",")

    init_db()
    db = SessionLocal()
    try:
        opps = generate_opportunities(
            db, category=args.category, top_n=args.top_n,
            our_source=args.our_source, competitor_sources=competitor_sources,
        )
        print(f"\nGenerated {len(opps)} opportunities: {args.our_source} vs {', '.join(competitor_sources)} ({args.category})\n")
        for o in opps:
            print(f"  {o.concept_name}: score={o.opportunity_score}")
            print(f"    {o.reason}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()