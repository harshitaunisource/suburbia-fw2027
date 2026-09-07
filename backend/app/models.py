"""
Database models for the Suburbia FW2027 Fashion Intelligence system.

Design notes:
- DATABASE_URL is read from env (see database.py). Defaults to a local SQLite
  file so the whole project is trivially portable / runnable with zero infra.
  Point it at a real Postgres instance for anything beyond local dev by
  setting DATABASE_URL=postgresql+psycopg2://user:pass@host/db
- image_kind on `products` implements the mandatory COMPETITOR / OUR_PRODUCT /
  CONCEPT distinction from the spec (section 3 / 18).

2026-09-07 CHANGES (unify Product / GenericProduct + real gender field):
- `Product` gained buyer_id / role / sub_category_id / source_config_id /
  pattern / color / gender -- the fields that used to only exist on
  GenericProduct. Going forward, app/services/generic_scraper.py writes
  into THIS table, not GenericProduct, so anything scraped from Search
  Products / Explore Categories / Add Brand shows up on the classic
  Products page, Market Analytics, and Buyer Opportunities automatically
  (they've always queried Product; they just never received these rows).
- `GenericSourceConfig` gained a real `gender` column. This directly
  fixes the Textilon men's/women's pajama collision: two source configs
  for the same brand + sub-category can now coexist distinguished by
  gender instead of colliding on (brand, sub_category_id) alone.
- GenericProduct / GenericScrapeRun are kept (not dropped) so existing
  rows and any code still reading them keep working, but they are no
  longer the write target for new scrapes -- see
  scripts/migrate_unify_and_add_gender.py for the one-time backfill of
  already-scraped GenericProduct rows into Product.
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


class Gender(str, enum.Enum):
    """Explicit garment-line field, added 2026-09-07 to fix a real,
    reproducible collision: Textilon's men's and women's pajamas were
    both scraped under the same (brand, sub_category) key with no way
    to tell them apart, so the second source silently overwrote/
    conflated the first. This lives on GenericSourceConfig (one field
    per brand+category source, set once when the URL is added) and is
    copied onto every Product row that source produces -- it is NOT
    guessed per-product from scraped text, because it describes user
    intent about which product line was searched, not something to
    infer from a page.
    """
    MENS = "MENS"
    WOMENS = "WOMENS"
    UNISEX = "UNISEX"
    KIDS = "KIDS"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
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

    # --- Unified 2026-09-07: fields that used to live only on
    # GenericProduct, now on the one table every consumer page reads.
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=True, index=True)
    role = Column(Enum(SourceRole), nullable=True, index=True)
    sub_category_id = Column(Integer, ForeignKey("item_hierarchy.id"), nullable=True, index=True)
    source_config_id = Column(Integer, ForeignKey("generic_source_configs.id"), nullable=True)
    gender = Column(Enum(Gender), nullable=True, index=True)
    pattern = Column(String(60))
    color = Column(String(60))

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
# CATEGORY HIERARCHY + BUYER/COMPETITOR SETUP
# (Buyer, GenericSourceConfig kept as the source-of-truth "what to scrape"
# config tables. GenericProduct/GenericScrapeRun kept for backward
# compatibility with pre-migration data -- new scrapes write to Product.)
# ============================================================================


class ItemHierarchy(Base):
    """One row per real (Item Type, Category, Sub Category) combination,
    seeded once from the uploaded Item_Category_SubCategory_Hierarchy.xlsx
    (see scripts/seed_item_hierarchy.py). This is what powers the three
    cascading dropdowns in the category-explorer UI."""
    __tablename__ = "item_hierarchy"

    id = Column(Integer, primary_key=True, index=True)
    item_type = Column(String(120), nullable=False, index=True)
    category = Column(String(160), nullable=False, index=True)
    sub_category = Column(String(160), nullable=False, index=True)
    sanity_keywords = Column(Text)


class Buyer(Base):
    """A brand we run this analysis for. Competitors are tracked
    per-buyer via GenericSourceConfig.buyer_id, so the same physical
    brand (e.g. Zara) could be tracked as a competitor under more than
    one buyer without the data colliding."""
    __tablename__ = "buyers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class GenericSourceConfig(Base):
    """A (brand, category URL, gender, link-discovery override) entry
    for one sub-category. `pdp_link_pattern` is now an OPTIONAL manual
    override -- see app/scrapers/link_discovery.py, which tries
    structural detection (JSON-LD ItemList, then URL-shape clustering)
    before ever falling back to a regex, so most brands no longer need
    this field populated at all.

    `gender` (added 2026-09-07): distinguishes multiple source configs
    for the same brand + sub-category that are genuinely different
    product lines (e.g. Textilon Men's Pajamas vs. Textilon Women's
    Pajamas) -- previously the only way to express this was smuggling
    it into the brand name or notes field, which is exactly what caused
    the real collision this fixes.
    """
    __tablename__ = "generic_source_configs"

    id = Column(Integer, primary_key=True, index=True)
    sub_category_id = Column(Integer, ForeignKey("item_hierarchy.id"), nullable=False, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False, index=True)
    role = Column(Enum(SourceRole), default=SourceRole.COMPETITOR, nullable=False, index=True)
    brand = Column(String(120), nullable=False)
    gender = Column(Enum(Gender), nullable=True, index=True)
    category_url = Column(Text, nullable=False)
    # Optional manual override -- see link_discovery.py. A reasonable
    # generic starting guess is offered by the API when none is
    # provided, but structural detection is tried first and usually
    # makes this unnecessary.
    pdp_link_pattern = Column(Text)
    # Manual fallback ONLY -- the real currency is now detected per-
    # product from the page itself (see currency_detect.py). This value
    # is used only when the page gives no usable signal at all.
    currency = Column(String(10), default="USD")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class GenericProduct(Base):
    """LEGACY table, kept read-only for backward compatibility with
    data scraped before the 2026-09-07 unification. New scrapes write
    directly to `Product` (see app/services/generic_scraper.py) so they
    appear on the classic Products / Market Analytics / Buyer
    Opportunities pages without a separate code path. Run
    scripts/migrate_unify_and_add_gender.py once to backfill any
    pre-existing rows here into `Product`.
    """
    __tablename__ = "generic_products"

    id = Column(Integer, primary_key=True, index=True)
    product_uid = Column(String(36), unique=True, index=True)
    sub_category_id = Column(Integer, ForeignKey("item_hierarchy.id"), nullable=False, index=True)
    source_config_id = Column(Integer, ForeignKey("generic_source_configs.id"), nullable=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=True, index=True)
    role = Column(Enum(SourceRole), nullable=True, index=True)
    gender = Column(Enum(Gender), nullable=True, index=True)
    brand = Column(String(120))
    product_name = Column(String(255), nullable=False)
    product_code = Column(String(120))
    product_url = Column(Text, nullable=False)
    image_url = Column(Text)
    local_image_path = Column(Text)
    price = Column(Float)
    original_price = Column(Float)
    currency = Column(String(10), default="USD")
    material = Column(Text)
    pattern = Column(String(60))
    color = Column(String(60))
    description = Column(Text)
    scraped_at = Column(DateTime, default=datetime.utcnow)


class GenericScrapeRun(Base):
    """Same role as ScrapeRun. Kept for historical runs recorded before
    the unification; new runs are also recorded here for the Data
    Collection UI regardless of which table the resulting products land
    in (see run_generic_scrape in generic_scraper.py)."""
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
    # Which link-discovery strategy actually worked for this run (see
    # app/scrapers/link_discovery.py) -- purely diagnostic, lets you see
    # at a glance whether a brand needed structural clustering or fell
    # all the way back to a regex, without digging through logs.
    link_discovery_strategy = Column(String(30))