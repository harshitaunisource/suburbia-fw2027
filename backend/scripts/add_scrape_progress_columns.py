"""
One-off: adds the live-progress columns to generic_scrape_runs
(candidates_total, current_step) so the frontend's polling loop can
show real step-by-step status instead of one static "please wait"
message.

Usage:
    cd backend
    python -m scripts.add_scrape_progress_columns
"""
from sqlalchemy import inspect, text

from app.database import SessionLocal, engine


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def migrate():
    db = SessionLocal()
    try:
        if not _column_exists("generic_scrape_runs", "candidates_total"):
            print("Adding generic_scrape_runs.candidates_total ...")
            db.execute(text("ALTER TABLE generic_scrape_runs ADD COLUMN candidates_total INTEGER"))
            db.commit()
        else:
            print("generic_scrape_runs.candidates_total already exists, skipping.")

        if not _column_exists("generic_scrape_runs", "current_step"):
            print("Adding generic_scrape_runs.current_step ...")
            db.execute(text("ALTER TABLE generic_scrape_runs ADD COLUMN current_step VARCHAR(160)"))
            db.commit()
        else:
            print("generic_scrape_runs.current_step already exists, skipping.")

        print("\nMigration complete.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()