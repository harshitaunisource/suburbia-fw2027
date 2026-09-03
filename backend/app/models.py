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
    # Stable, globally-unique identifier independent of the auto-increment
    # `id` -- added 2026-08-31 so this project can cross-reference a
    # specific product across future systems (inventory, buyer-selection
    # mapping) without depending on database-internal row ids, which
    # could change if data is ever migrated/re-imported. Generated once
    # at insert time and never changed. See
    # scripts/migrate_add_currency_and_uid.py for the one-time backfill
    # this required on the already-populated production table.
    product_uid = Column(String(36), unique=True, index=True)
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
    # Added 2026-08-31 -- fixes a real bug where a competitor's price in
    # any non-USD currency (confirmed live: Zara priced in INR) got
    # displayed with a hardcoded "$" in the generated PPT, since this
    # column did not previously exist at all and the currency
    # information was silently dropped when copying a reference product
    # in via the "Suggest Products" workflow. See
    # scripts/migrate_add_currency_and_uid.py for the one-time migration
    # this required on the already-populated production table.
    currency = Column(String(10), default="USD")
    source_ref = Column(String(64), unique=True, index=True, nullable=True)
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


# ============================================================================
# GENERIC CATEGORY EXPLORER (new feature, added 2026-08-28)
#
# Deliberately a SEPARATE, standalone set of tables -- not reusing Product /
# ScrapeRun / ProductOpportunity / CatalogueProduct at all. This is a new,
# unrelated feature (search-and-scrape any item category, any brand, no
# comparison baseline) sitting alongside the original Suburbia FW2027
# gap-analysis feature, which stays completely untouched: none of the
# existing tables' schemas, data, or code paths are modified by anything
# below. Keeps the two feature sets impossible to accidentally cross-
# contaminate.
# ============================================================================


class ItemHierarchy(Base):
    """One row per real (Item Type, Category, Sub Category) combination,
    seeded once from the uploaded Item_Category_SubCategory_Hierarchy.xlsx
    (see scripts/seed_item_hierarchy.py). This is what powers the three
    cascading dropdowns in the new category-explorer UI."""
    __tablename__ = "item_hierarchy"

    id = Column(Integer, primary_key=True, index=True)
    item_type = Column(String(120), nullable=False, index=True)
    category = Column(String(160), nullable=False, index=True)
    sub_category = Column(String(160), nullable=False, index=True)
    # Comma-separated keywords used to sanity-check that a scraped product
    # actually belongs to this sub-category (same defensive pattern already
    # proven necessary on the Suburbia side -- see
    # _generic_playwright_template.py's CATEGORY_SANITY_KEYWORDS, which
    # caught real contamination live on Target). Pre-filled with a
    # best-guess for common sub-categories; editable via the API since no
    # keyword list can be complete for 469 possible sub-categories without
    # real usage data to refine it.
    sanity_keywords = Column(Text)

class SourceRole(str, enum.Enum):
    """Every brand tracked in the system is either:
    - BUYER: the company we're doing this analysis for (e.g. Suburbia,
      Textilon). Its own product URLs are scraped the same way as any
      competitor's, just tagged differently so the UI can show "your
      products" vs. "their products" separately.
    - COMPETITOR: a brand being tracked *against* one specific buyer.
      Always has a buyer_id pointing at the buyer it's a competitor of --
      the same competitor brand (e.g. Zara) could in principle be added
      again under a different buyer later without conflict, since each
      row is scoped to one buyer.
    """
    BUYER = "BUYER"
    COMPETITOR = "COMPETITOR"


class Buyer(Base):
    """A brand we run this analysis for (added 2026-09-03 so buyers are no
    longer hardcoded -- 'Suburbia' and 'Textilon' are just the first two
    rows here, not special-cased anywhere in code). Competitors are
    tracked per-buyer via GenericSourceConfig.buyer_id, so the same
    physical brand (e.g. Zara) could be tracked as a competitor under more
    than one buyer without the data colliding."""
    __tablename__ = "buyers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class GenericSourceConfig(Base):
    """A human-curated (brand, category URL, link-discovery pattern) entry
    for one sub-category. THIS is the piece that cannot be auto-generated:
    exactly as happened repeatedly on the Suburbia side of this project, a
    generic 'any href that looks product-shaped' pattern reliably fails
    against real sites until verified against real HTML. Adding a new
    brand for a sub-category is expected to follow the same loop already
    used throughout this project: try a starting pattern, inspect the
    debug HTML dump on failure, tighten the pattern from real evidence."""
    __tablename__ = "generic_source_configs"

    id = Column(Integer, primary_key=True, index=True)
    sub_category_id = Column(Integer, ForeignKey("item_hierarchy.id"), nullable=False, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False, index=True)
    role = Column(Enum(SourceRole), default=SourceRole.COMPETITOR, nullable=False, index=True)
    brand = Column(String(120), nullable=False)
    category_url = Column(Text, nullable=False)
    # Regex (as a plain string) matching product-detail-page hrefs on this
    # specific site -- same role as each hardcoded PDP_LINK_RE in the
    # Suburbia scrapers, just made data-driven instead of one Python file
    # per site. A reasonable generic starting guess is offered by the API
    # when none is provided, but -- per the above -- expect to need to
    # tighten it from a real debug HTML dump before it reliably works.
    pdp_link_pattern = Column(Text)
    currency = Column(String(10), default="USD")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class GenericProduct(Base):
    """A scraped product for the generic category explorer. Deliberately
    NOT the same table as Product (Suburbia's own products table) -- no
    shared schema, no shared ids, no risk of one feature's data leaking
    into or being confused with the other's."""
    __tablename__ = "generic_products"

    id = Column(Integer, primary_key=True, index=True)
    product_uid = Column(String(36), unique=True, index=True)
    sub_category_id = Column(Integer, ForeignKey("item_hierarchy.id"), nullable=False, index=True)
    source_config_id = Column(Integer, ForeignKey("generic_source_configs.id"), nullable=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=True, index=True)
    role = Column(Enum(SourceRole), nullable=True, index=True)
    brand = Column(String(120))
    product_name = Column(String(255), nullable=False)
    product_code = Column(String(120))
    product_url = Column(Text, nullable=False)
    image_url = Column(Text)
    local_image_path = Column(Text)
    price = Column(Float)
    # Populated only when the item is actually on sale -- see
    # app/services/pricing.py's compute_mrp(), which is the ONLY
    # sanctioned way to derive a usable price anywhere in this project.
    # Never read `price` directly for a business purpose; always go
    # through compute_mrp(price, original_price).
    original_price = Column(Float)
    currency = Column(String(10), default="USD")
    # Explicit scope per project requirements: composition/material,
    # pattern, and color are captured where available; anything else
    # (e.g. model/fit-on-model details) is deliberately NOT scraped or
    # stored. composition + price + image + name are the mandatory
    # fields for a product to be usable -- see generic_scraper.py's
    # validation before a row is saved.
    material = Column(Text)   # composition, e.g. "80% Cotton 20% Polyester"
    pattern = Column(String(60))
    color = Column(String(60))
    description = Column(Text)
    scraped_at = Column(DateTime, default=datetime.utcnow)


class GenericScrapeRun(Base):
    """Same role as ScrapeRun, but for the generic category explorer --
    kept separate so the existing Data Collection page's queries/behavior
    for Suburbia's 10 sources are never affected by this feature."""
    __tablename__ = "generic_scrape_runs"

    id = Column(Integer, primary_key=True, index=True)
    sub_category_id = Column(Integer, ForeignKey("item_hierarchy.id"), nullable=False, index=True)
    source_config_id = Column(Integer, ForeignKey("generic_source_configs.id"), nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    products_found = Column(Integer, default=0)
    products_new = Column(Integer, default=0)
    images_downloaded = Column(Integer, default=0)
    images_failed = Column(Integer, default=0)
    status = Column(String(20), default="running")  # running | success | failed
    error_message = Column(Text)