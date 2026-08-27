"""
Database models for the Suburbia FW2027 Fashion Intelligence system.

Design notes:
- DATABASE_URL is read from env (see database.py). Defaults to a local SQLite
  file so the whole project is trivially portable / runnable with zero infra.
  Point it at a real Postgres instance for anything beyond local dev by
  setting DATABASE_URL=postgresql+psycopg2://user:pass@host/db
- image_kind on `products` implements the mandatory COMPETITOR / OUR_PRODUCT /
  CONCEPT distinction from the spec (section 3 / 18).
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import relationship

from app.database import Base


class ImageKind(str, enum.Enum):
    COMPETITOR = "COMPETITOR_IMAGE"
    OUR_PRODUCT = "OUR_PRODUCT_IMAGE"
    CONCEPT = "CONCEPT_IMAGE"


class OpportunityStatus(str, enum.Enum):
    identified = "identified"
    shortlisted = "shortlisted"
    selected = "selected"
    rejected = "rejected"
    catalogue = "catalogue"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False, index=True)  # e.g. "suburbia", "zara"
    brand = Column(String(120))
    category = Column(String(80), index=True)     # sweaters | blouses
    subcategory = Column(String(120))
    product_name = Column(String(500), nullable=False)
    product_code = Column(String(120), index=True)  # site-native SKU / product id
    product_url = Column(Text, nullable=False)
    image_url = Column(Text)
    local_image_path = Column(Text)
    thumbnail_path = Column(Text)
    image_kind = Column(Enum(ImageKind), default=ImageKind.COMPETITOR, nullable=False)

    price = Column(Float)
    currency = Column(String(8), default="MXN")
    original_price = Column(Float)
    discount_price = Column(Float)
    discount_percentage = Column(Float)

    description = Column(Text)
    material = Column(Text)
    sizes = Column(Text)      # comma-separated; kept simple for MVP
    colors = Column(Text)     # comma-separated
    availability = Column(String(50))

    scraped_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    attributes = relationship("ProductAttributes", back_populates="product", uselist=False)


class ProductAttributes(Base):
    __tablename__ = "product_attributes"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, unique=True)

    fit = Column(String(60))
    silhouette = Column(String(60))
    neckline = Column(String(60))
    sleeve_type = Column(String(60))
    length = Column(String(60))
    pattern = Column(String(60))
    primary_color = Column(String(60))
    secondary_color = Column(String(60))
    fabric_type = Column(String(60))
    texture = Column(String(60))
    style = Column(String(60))
    details = Column(Text)
    season = Column(String(30))
    ai_confidence = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="attributes")


class ProductOpportunity(Base):
    __tablename__ = "product_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(80), index=True)
    concept_name = Column(String(255), nullable=False)

    trend_score = Column(Float)
    competitor_score = Column(Float)
    suburbia_gap_score = Column(Float)
    price_score = Column(Float)
    commercial_score = Column(Float)
    opportunity_score = Column(Float)

    reason = Column(Text)
    status = Column(Enum(OpportunityStatus), default=OpportunityStatus.identified, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class CatalogueProduct(Base):
    __tablename__ = "catalogue_products"

    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("product_opportunities.id"))

    product_name = Column(String(255), nullable=False)
    our_product_code = Column(String(120))
    category = Column(String(80))
    description = Column(Text)
    image_path = Column(Text)      # must be OUR_PRODUCT or CONCEPT image only
    image_kind = Column(Enum(ImageKind), default=ImageKind.OUR_PRODUCT, nullable=False)
    additional_image_paths = Column(Text)  # comma-separated, same rule as image_path
    colorways = Column(Text)
    fabric = Column(Text)
    size_range = Column(String(120))
    target_price = Column(Float)
    moq = Column(Integer)
    lead_time = Column(String(60))
    packaging = Column(Text)
    notes = Column(Text)
    sort_order = Column(Integer, default=0)
    approved = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class ScrapeRun(Base):
    """Not in the original spec table list, but required to power the
    'Data Collection' dashboard (source / category / products / last run / status)."""
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False, index=True)
    category = Column(String(80), nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    products_found = Column(Integer, default=0)
    products_new = Column(Integer, default=0)
    products_updated = Column(Integer, default=0)
    images_downloaded = Column(Integer, default=0)
    images_failed = Column(Integer, default=0)
    duplicates_skipped = Column(Integer, default=0)
    status = Column(String(20), default="running")  # running | success | failed
    error_message = Column(Text)
