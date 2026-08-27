"""
Phase 10: Buyer Catalogue generator (spec sections 16-18) -- now produces
a PowerPoint deck (per your workflow: shortlisted Opportunity -> pick the
closest real competitor product -> straight into the deck) instead of a
PDF built from hand-entered products.

IP / COPYRIGHT NOTE (read before sending anything this generates to an
external buyer): when a catalogue entry was created by picking a
competitor's own product as a stand-in (via
POST /api/catalogue/products/from-product), its photo is someone else's
product photography, not Suburbia's. This generator will still place
that image on the slide -- your call, you asked for speed over waiting
for original photography -- but it stamps a visible
"REFERENCE -- competitor sourced" label directly on the image so nobody
downstream mistakes it for an approved Suburbia product photo. Swap in a
real photo via the Our Products page (upload -> OUR_PRODUCT kind) before
this goes external, and the label disappears automatically.

This module only ever reads from CatalogueProduct rows with
approved=True. It never touches Product, ProductAttributes, or
ProductOpportunity data directly, so competitor prices, URLs, or
internal opportunity scores can't leak into the deck -- only whatever a
CatalogueProduct row explicitly carries (spec section 17).
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Optional

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt
from sqlalchemy.orm import Session

from app.models import CatalogueProduct, ImageKind
from app.scrapers.base import STORAGE_ROOT

OUTPUT_DIR = Path(os.getenv("CATALOGUE_OUTPUT_DIR", STORAGE_ROOT / "catalogue"))

# 16:9 widescreen, matches modern PowerPoint default
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

CHARCOAL = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x6B, 0x6B, 0x6B)
WARN = RGBColor(0xB4, 0x3A, 0x1F)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG = RGBColor(0xFA, 0xFA, 0xFA)


def _blank_slide(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])  # 6 = fully blank layout


def _add_text(slide, left, top, width, height, text, size=18, bold=False, color=CHARCOAL, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def _resolve_image_path(path: Optional[str]) -> Optional[Path]:
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = STORAGE_ROOT.parent / path
    return p if p.exists() else None


def generate_catalogue_pptx(
    db: Session,
    collection_title: str = "SUBURBIA MEXICO",
    season_title: str = "FW2027 WOMEN'S COLLECTION",
    market_direction: Optional[str] = None,
) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"FW2027_Buyer_Catalogue_{date.today().isoformat()}.pptx"
    filepath = OUTPUT_DIR / filename

    products = (
        db.query(CatalogueProduct)
        .filter(CatalogueProduct.approved.is_(True))
        .order_by(CatalogueProduct.sort_order, CatalogueProduct.id)
        .all()
    )

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # ---------------------------------------------------------------- cover
    slide = _blank_slide(prs)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = CHARCOAL
    _add_text(slide, Inches(1), Inches(2.8), Inches(11), Inches(1.2), collection_title,
               size=44, bold=True, color=WHITE)
    _add_text(slide, Inches(1), Inches(3.8), Inches(11), Inches(0.8), season_title,
               size=20, color=RGBColor(0xCC, 0xCC, 0xCC))

    # ------------------------------------------------------- market direction
    slide = _blank_slide(prs)
    _add_text(slide, Inches(0.7), Inches(0.5), Inches(11.9), Inches(0.7), "Market Direction",
               size=28, bold=True)
    _add_text(
        slide, Inches(0.7), Inches(1.4), Inches(11.9), Inches(2.5),
        market_direction
        or "This season's collection responds to emerging silhouettes and styling "
        "directions observed across the women's sweater and blouse market, curated "
        "into a focused, commercially-ready assortment.",
        size=16,
    )

    sweater_count = sum(1 for p in products if p.category == "sweaters")
    blouse_count = sum(1 for p in products if p.category == "blouses")
    colorways = sorted({c.strip() for p in products if p.colorways for c in p.colorways.split(",") if c.strip()})

    _add_text(slide, Inches(0.7), Inches(3.3), Inches(11.9), Inches(0.5), "Collection Overview",
               size=22, bold=True)
    overview_lines = [
        f"Total Styles: {len(products)}",
        f"Sweater Styles: {sweater_count}",
        f"Blouse Styles: {blouse_count}",
        f"Key Colors: {', '.join(colorways[:8]) if colorways else '—'}",
    ]
    _add_text(slide, Inches(0.7), Inches(4.0), Inches(11.9), Inches(2.5), "\n".join(overview_lines), size=15)

    # ------------------------------------------------------------ product slides
    for p in products:
        slide = _blank_slide(prs)

        img_path = _resolve_image_path(p.image_path)
        if img_path:
            pic = slide.shapes.add_picture(str(img_path), Inches(0.7), Inches(0.7), height=Inches(5.6))
            if p.image_kind == ImageKind.COMPETITOR:
                # Visible, unmissable label -- this image is someone
                # else's product photography, kept here only because it
                # was explicitly chosen as a fast reference stand-in
                # (see the from-product endpoint's docstring). Swapping
                # in a real photo via Our Products removes this.
                label_top = pic.top + pic.height - Inches(0.45)
                label = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, pic.left, label_top, pic.width, Inches(0.45))
                label.fill.solid()
                label.fill.fore_color.rgb = WARN
                label.line.fill.background()
                tf = label.text_frame
                tf.word_wrap = True
                para = tf.paragraphs[0]
                para.alignment = PP_ALIGN.CENTER
                run = para.add_run()
                run.text = "REFERENCE — competitor sourced"
                run.font.size = Pt(12)
                run.font.bold = True
                run.font.color.rgb = WHITE
        else:
            placeholder = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.7), Inches(0.7), Inches(5.6), Inches(5.6))
            placeholder.fill.solid()
            placeholder.fill.fore_color.rgb = RGBColor(0xEE, 0xEE, 0xEE)
            placeholder.line.color.rgb = RGBColor(0xDD, 0xDD, 0xDD)
            tf = placeholder.text_frame
            para = tf.paragraphs[0]
            para.alignment = PP_ALIGN.CENTER
            run = para.add_run()
            run.text = "No image yet"
            run.font.size = Pt(14)
            run.font.color.rgb = MUTED

        text_left = Inches(6.6)
        text_width = Inches(6.0)
        _add_text(slide, text_left, Inches(0.7), text_width, Inches(0.9), p.product_name, size=24, bold=True)
        if p.our_product_code:
            _add_text(slide, text_left, Inches(1.5), text_width, Inches(0.4),
                       f"Code: {p.our_product_code}", size=11, color=MUTED)

        detail_lines = []
        if p.description:
            detail_lines.append(p.description)
            detail_lines.append("")
        if p.colorways:
            detail_lines.append(f"Colorways: {p.colorways}")
        if p.fabric:
            detail_lines.append(f"Fabric: {p.fabric}")
        if p.size_range:
            detail_lines.append(f"Size Range: {p.size_range}")
        if p.target_price:
            detail_lines.append(f"Target Price: ${p.target_price:,.2f}")
        if p.moq:
            detail_lines.append(f"MOQ: {p.moq}")
        if p.lead_time:
            detail_lines.append(f"Lead Time: {p.lead_time}")

        _add_text(slide, text_left, Inches(2.0), text_width, Inches(4.5), "\n".join(detail_lines), size=14)

    # ------------------------------------------------------------------ final
    slide = _blank_slide(prs)
    _add_text(slide, Inches(1), Inches(2.5), Inches(11), Inches(0.8), "Next Steps", size=32, bold=True)
    steps = ["Sample Selection", "Commercial Discussion", "Style Confirmation", "Order Placement"]
    _add_text(slide, Inches(1), Inches(3.5), Inches(11), Inches(2.5), "  →  ".join(steps), size=18)

    prs.save(str(filepath))
    return str(filepath)