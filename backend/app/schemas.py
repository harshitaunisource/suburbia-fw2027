from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    brand: Optional[str]
    category: Optional[str]
    product_name: str
    product_code: Optional[str]
    product_url: str
    image_url: Optional[str]
    local_image_path: Optional[str]
    price: Optional[float]
    currency: Optional[str]
    original_price: Optional[float]
    discount_percentage: Optional[float]
    availability: Optional[str]
    scraped_at: Optional[datetime]


class ScrapeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    category: str
    started_at: datetime
    finished_at: Optional[datetime]
    products_found: int
    products_new: int
    products_updated: int
    images_downloaded: int
    images_failed: int
    duplicates_skipped: int
    status: str
    error_message: Optional[str]


class RunScrapeRequest(BaseModel):
    source: str
    category: str
    category_url: str
    max_pages: Optional[int] = None


class DashboardStats(BaseModel):
    products_analysed: int
    images_collected: int
    ai_classified: int
    opportunities: int
    shortlisted_styles: int
    catalogue_styles: int


class RunAttributeExtractionRequest(BaseModel):
    category: Optional[str] = None
    limit: int = 500


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    concept_name: str
    trend_score: Optional[float]
    competitor_score: Optional[float]
    suburbia_gap_score: Optional[float]
    price_score: Optional[float]
    commercial_score: Optional[float]
    opportunity_score: Optional[float]
    reason: Optional[str]
    status: str
    created_at: datetime


class OpportunityStatusUpdate(BaseModel):
    status: str  # identified | shortlisted | selected | rejected | catalogue


class GenerateOpportunitiesRequest(BaseModel):
    category: str
    top_n: int = 15


class CatalogueProductIn(BaseModel):
    opportunity_id: Optional[int] = None
    product_name: str
    our_product_code: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    colorways: Optional[str] = None
    fabric: Optional[str] = None
    size_range: Optional[str] = None
    target_price: Optional[float] = None
    moq: Optional[int] = None
    lead_time: Optional[str] = None
    packaging: Optional[str] = None
    notes: Optional[str] = None
    sort_order: int = 0


class CatalogueProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opportunity_id: Optional[int]
    product_name: str
    our_product_code: Optional[str]
    category: Optional[str]
    description: Optional[str]
    image_path: Optional[str]
    image_kind: str
    colorways: Optional[str]
    fabric: Optional[str]
    size_range: Optional[str]
    target_price: Optional[float]
    moq: Optional[int]
    lead_time: Optional[str]
    packaging: Optional[str]
    notes: Optional[str]
    sort_order: int
    approved: bool
    created_at: datetime


class CatalogueProductFromProductRequest(BaseModel):
    opportunity_id: int
    product_id: int


class GenerateCatalogueRequest(BaseModel):
    collection_title: str = "SUBURBIA MEXICO"
    season_title: str = "FW2027 WOMEN'S COLLECTION"
    market_direction: Optional[str] = None