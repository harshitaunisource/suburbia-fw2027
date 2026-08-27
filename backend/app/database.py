import os

from dotenv import load_dotenv

load_dotenv()  # picks up a local .env file if present; no-op otherwise

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Portable by default: SQLite file, zero setup.
# For real use, set DATABASE_URL to Postgres, e.g.:
#   postgresql+psycopg2://suburbia:suburbia@localhost:5432/suburbia_fw2027
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./suburbia_fw2027.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    # pool_pre_ping: tests every connection with a lightweight query
    # before actually using it, and transparently reconnects if it was
    # dropped -- this is the standard fix for cloud Postgres providers
    # (Neon, RDS, etc.) that silently close idle connections. Confirmed
    # live: a long image-download loop (dozens of sequential network
    # round-trips with no SQL activity in between) gave Neon's free-tier
    # pooler enough idle time to drop the connection mid-run, crashing
    # with "SSL connection has been closed unexpectedly" -- with no
    # retry logic, every query on that same Session after the drop
    # failed too. Only applies to real network databases; harmless no-op
    # for SQLite.
    pool_pre_ping=(not DATABASE_URL.startswith("sqlite")),
    # Proactively recycle connections older than 5 minutes, before Neon's
    # own idle timeout has a chance to drop them out from under us.
    pool_recycle=300 if not DATABASE_URL.startswith("sqlite") else -1,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Import models so they're registered on Base before create_all
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
