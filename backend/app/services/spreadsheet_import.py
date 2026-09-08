"""
Reusable spreadsheet importer -- lets a person upload a CSV or XLSX
export (e.g. from the "Web Scraper" Chrome extension) directly through
the UI and have it parsed into real Product rows, instead of every new
brand needing a hand-written one-off Python script (which is what the
Textilon import was, and what the H&M/Coppel/Zara CSVs would have
needed too -- the H&M export alone is ~600 rows, well past what's
practical to hand-transcribe).

Column layout is NOT assumed -- every export this project has seen so
far (Textilon, H&M, Coppel, Zara) uses a different column order, since
the Chrome extension exports columns in whatever order they were
clicked in per scraping session. So the caller specifies which column
number holds what (1-indexed, matching how a person would count
columns in Excel/Sheets by eye), rather than this code guessing.

No product detail-page URL is assumed to be present (confirmed: none
of the CSVs collected so far have one, only the category page URL and
each product's image). product_url falls back to the image URL itself
when no explicit URL column is given -- still a real, unique, clickable
link, just to the image rather than a full product page.

Currency is NOT taken as a single fixed value for the whole file --
each row's price text is run through the exact same detect_currency()
the live scraper uses (symbol + URL-locale aware, including the MX
path/domain fixes from 2026-09-08), using the sheet's own category URL
for context. This is what actually prevents the "Mexican $ silently
counted as US $" risk -- both use the same bare "$" symbol, and only
the URL/locale context tells them apart. A currency value is still
accepted as the final fallback, for the rare row where even that
can't resolve anything.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.database import get_db  # noqa: F401  (kept for symmetry with other services; not used directly)
from app.models import (
    Buyer,
    Gender,
    GenericSourceConfig,
    ImageKind,
    ItemHierarchy,
    Product,
    SourceRole,
)
from app.scrapers.currency_detect import detect_currency

PRICE_NUMBER_RE = re.compile(r"[\d,]+\.?\d*")


@dataclass
class SpreadsheetImportResult:
    inserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_price(raw: Optional[str]) -> Optional[float]:
    """Pulls the first plausible number out of a raw price cell --
    handles "$499", "£14.99", "MXN 279.30", "Desde $12 quincenal", etc.
    Returns None (never 0 or a guess) if nothing numeric is found."""
    if not raw:
        return None
    match = PRICE_NUMBER_RE.search(raw.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _read_rows(filename: str, content: bytes) -> list[list[str]]:
    """Returns every row as a list of string cells, for either a CSV
    or an XLSX file -- caller strips the header row itself if needed."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")  # utf-8-sig strips a leading BOM if present
        reader = csv.reader(io.StringIO(text))
        return [row for row in reader]

    if lower.endswith(".xlsx"):
        try:
            import openpyxl
        except ImportError as e:
            raise ValueError(
                "XLSX support needs the 'openpyxl' package -- add `openpyxl` to requirements.txt "
                "and reinstall, or export/save the file as .csv instead."
            ) from e
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = wb.worksheets[0]
        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(["" if cell is None else str(cell) for cell in row])
        return rows

    raise ValueError(f"Unsupported file type: {filename} -- please upload a .csv or .xlsx file.")


def get_or_create_source_for_import(
    db: Session,
    brand: str,
    hierarchy: ItemHierarchy,
    gender: Optional[Gender],
    role: SourceRole,
    buyer: Optional[Buyer],
    category_url: str,
    currency: str,
) -> GenericSourceConfig:
    existing = (
        db.query(GenericSourceConfig)
        .filter(
            GenericSourceConfig.sub_category_id == hierarchy.id,
            GenericSourceConfig.brand.ilike(brand.strip()),
            GenericSourceConfig.gender == gender,
        )
        .first()
    )
    if existing:
        changed = False
        if buyer and existing.buyer_id != buyer.id:
            existing.buyer_id = buyer.id
            changed = True
        if buyer and existing.role != SourceRole.BUYER:
            existing.role = SourceRole.BUYER
            changed = True
        if changed:
            db.commit()
        return existing

    source = GenericSourceConfig(
        sub_category_id=hierarchy.id,
        buyer_id=buyer.id if buyer else None,
        role=role,
        gender=gender,
        brand=brand.strip(),
        category_url=category_url,
        currency=currency,
        notes="Imported via spreadsheet upload.",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def import_spreadsheet(
    db: Session,
    *,
    filename: str,
    content: bytes,
    brand: str,
    sub_category_id: int,
    role: SourceRole = SourceRole.COMPETITOR,
    gender: Optional[Gender] = None,
    buyer_id: Optional[int] = None,
    buyer_name: Optional[str] = None,
    currency_fallback: str = "USD",
    has_header_row: bool = True,
    name_col: int = 1,
    price_col: Optional[int] = None,
    original_price_col: Optional[int] = None,
    image_col: Optional[int] = None,
    product_url_col: Optional[int] = None,
    category_url_override: Optional[str] = None,
) -> SpreadsheetImportResult:
    """`*_col` values are 1-INDEXED (column 1 is the first column) to
    match how a person counts columns by eye in Excel/Sheets/a CSV
    viewer -- converted to 0-indexed internally."""
    result = SpreadsheetImportResult()

    hierarchy = db.get(ItemHierarchy, sub_category_id)
    if not hierarchy:
        result.errors.append(f"sub_category_id {sub_category_id} not found.")
        return result

    buyer = None
    if buyer_id:
        buyer = db.get(Buyer, buyer_id)
    elif buyer_name:
        buyer = db.query(Buyer).filter(Buyer.name.ilike(buyer_name.strip())).first()
        if not buyer:
            buyer = Buyer(name=buyer_name.strip())
            db.add(buyer)
            db.commit()
            db.refresh(buyer)
    if buyer:
        role = SourceRole.BUYER

    rows = _read_rows(filename, content)
    if has_header_row and rows:
        rows = rows[1:]

    # Try to recover the sheet's own category URL from a
    # "web_scraper_start_url"-style export if one wasn't explicitly
    # given -- every CSV collected so far has this in column 2. Falls
    # back to a placeholder if genuinely not findable; only used for
    # currency-locale detection and the source config's category_url,
    # never required to be a real live page.
    category_url = category_url_override
    if not category_url and rows and len(rows[0]) > 1:
        candidate = rows[0][1].strip()
        if candidate.startswith("http"):
            category_url = candidate
    category_url = category_url or f"https://unknown-source.invalid/{brand.lower().replace(' ', '-')}"

    source = get_or_create_source_for_import(
        db, brand, hierarchy, gender, role, buyer, category_url, currency_fallback
    )

    def cell(row: list[str], col: Optional[int]) -> Optional[str]:
        if not col or col < 1 or col > len(row):
            return None
        value = row[col - 1].strip()
        return value or None

    for row_num, row in enumerate(rows, start=(2 if has_header_row else 1)):
        if not row or all(not c.strip() for c in row):
            continue
        try:
            name = cell(row, name_col)
            if not name:
                result.errors.append(f"Row {row_num}: no name found in column {name_col}, skipped.")
                continue

            price_raw = cell(row, price_col)
            original_price_raw = cell(row, original_price_col)
            image_url = cell(row, image_col)
            explicit_url = cell(row, product_url_col)

            price = _parse_price(price_raw)
            original_price = _parse_price(original_price_raw)
            # A common export shape (confirmed live on Coppel/Textilon):
            # the "current" and "original" price columns can arrive
            # swapped depending on click order -- if what we parsed as
            # "original" is actually smaller, they were reversed.
            if price is not None and original_price is not None and original_price < price:
                price, original_price = original_price, price

            resolved_currency = None
            if price_raw:
                resolved_currency = detect_currency(
                    price_text=price_raw, url=category_url, fallback=currency_fallback
                )
            currency = resolved_currency or currency_fallback

            product_url = explicit_url or image_url
            if not product_url:
                result.errors.append(f"Row {row_num} ('{name}'): no URL or image to use as a link, skipped.")
                continue

            existing = db.query(Product).filter(Product.product_url == product_url).first()
            if existing:
                result.skipped += 1
                continue

            db.add(
                Product(
                    product_uid=str(uuid.uuid4()),
                    source=brand.lower().replace(" ", "_"),
                    brand=brand,
                    category=hierarchy.sub_category.lower(),
                    subcategory=hierarchy.category,
                    sub_category_id=hierarchy.id,
                    source_config_id=source.id,
                    buyer_id=buyer.id if buyer else None,
                    role=role,
                    image_kind=ImageKind.OUR_PRODUCT if buyer else ImageKind.COMPETITOR,
                    gender=gender,
                    product_name=name,
                    product_code=None,
                    product_url=product_url,
                    image_url=image_url,
                    price=price,
                    original_price=original_price,
                    currency=currency,
                    availability="in_stock",
                    scraped_at=datetime.utcnow(),
                )
            )
            result.inserted += 1
        except Exception as e:
            result.errors.append(f"Row {row_num}: unexpected error -- {e}")
            continue

    db.commit()
    return result