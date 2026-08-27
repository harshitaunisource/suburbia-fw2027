"""
Optional demo/dev helper: seeds a handful of realistic-shaped Suburbia +
competitor products directly into the database via the ORM (bypassing
the scrapers entirely).

WHY THIS EXISTS: the scrapers need real internet access to real retail
sites to do anything, which this build/test environment doesn't have.
This script lets you exercise every downstream phase of the pipeline --
AI attribute extraction, analytics, gap analysis, opportunity scoring,
our-product entry, and PDF catalogue generation -- and see the UI
populated with data, without waiting on/debugging live scrapers first.

This is NOT scraped data and must never be mistaken for it -- everything
it inserts uses source names prefixed nowhere near real scrape output,
and running the real scrapers (Data Collection page) will not touch or
need this data at all.

Usage:
    cd backend && python -m scripts.seed_demo_data
"""
import random
from datetime import datetime, timedelta

from app.database import SessionLocal, init_db
from app.models import Product

random.seed(42)

SWEATER_NAMES = [
    ("Oversized V-Neck Sweater", "oversized fit, v-neck, long sleeve, solid burgundy knit"),
    ("Striped Crew Neck Sweater", "regular fit, crew neck, long sleeve, striped cream and navy knit"),
    ("Polo Collar Ribbed Sweater", "slim fit, polo neckline, long sleeve, solid black knit"),
    ("Cable Knit Turtleneck", "relaxed fit, turtleneck, long sleeve, cable knit texture, grey"),
    ("Cropped Cardigan", "cropped fit, v-neck, long sleeve, solid beige knit"),
    ("Floral Jacquard Sweater", "regular fit, crew neck, long sleeve, floral pattern, green"),
    ("Batwing Sleeve Sweater", "oversized fit, off shoulder, batwing sleeve, solid brown knit"),
    ("Checked Wool Sweater", "regular fit, crew neck, long sleeve, check pattern, navy wool"),
]
BLOUSE_NAMES = [
    ("Satin Long Sleeve Blouse", "regular fit, v-neck, long sleeve, solid cream satin"),
    ("Chiffon Ruffle Blouse", "relaxed fit, boat neck, short sleeve, floral pattern, pink chiffon"),
    ("Cotton Button-Up Blouse", "slim fit, crew neck, long sleeve, striped white and blue cotton"),
    ("Sleeveless Silk Top", "regular fit, square neck, sleeveless, solid black silk"),
    ("Polka Dot Blouse", "relaxed fit, v-neck, 3/4 sleeve, polka dot pattern, navy"),
]

BRANDS = {
    "suburbia": None,
    "zara": "Zara",
    "hm": "H&M",
    "c_and_a": "C&A",
    "primark": "Primark",
    "target": "Target",
    "old_navy": "Old Navy",
    "shein": "SHEIN",
    "boohoo": "Boohoo",
    "asos": "ASOS",
}


def seed():
    init_db()
    db = SessionLocal()
    count = 0
    try:
        for source, brand in BRANDS.items():
            # Suburbia intentionally under-represents a few trending
            # concepts (oversized, striped, polo) to produce a realistic,
            # non-trivial gap analysis / opportunity result -- exactly
            # the scenario spec section 11's example table describes.
            pool = SWEATER_NAMES + BLOUSE_NAMES
            n = 6 if source == "suburbia" else random.randint(8, 14)
            sample = random.sample(pool, min(n, len(pool))) if n <= len(pool) else [
                random.choice(pool) for _ in range(n)
            ]

            for i, (name, desc) in enumerate(sample):
                if source == "suburbia" and any(k in name.lower() for k in ["oversized", "striped", "polo"]):
                    if random.random() < 0.7:
                        continue  # simulate Suburbia's real assortment gap

                category = "sweaters" if (name, desc) in SWEATER_NAMES else "blouses"
                base_price = random.uniform(400, 1200) if source == "suburbia" else random.uniform(300, 1500)
                code = f"{source.upper()}-{category[:3].upper()}-{i:03d}"

                db.add(
                    Product(
                        source=source,
                        brand=brand,
                        category=category,
                        subcategory=None,
                        product_name=f"{name} ({source})",
                        product_code=code,
                        product_url=f"https://example-{source}.invalid/product/{code}",
                        image_url=None,
                        local_image_path=None,
                        price=round(base_price, 2),
                        currency="MXN" if source in ("suburbia", "c_and_a", "old_navy") else "USD",
                        description=desc,
                        scraped_at=datetime.utcnow() - timedelta(days=random.randint(0, 5)),
                    )
                )
                count += 1
        db.commit()
        print(f"Seeded {count} demo products across {len(BRANDS)} sources.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
