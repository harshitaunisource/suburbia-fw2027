from app.scrapers.base import BaseScraper
from app.scrapers.suburbia import SuburbiaScraper
from app.scrapers.hm import HMScraper
from app.scrapers.old_navy import OldNavyScraper
from app.scrapers.c_and_a import CAndAScraper
from app.scrapers.zara import ZaraScraper
from app.scrapers.primark import PrimarkScraper
from app.scrapers.target import TargetScraper
from app.scrapers.shein import SheinScraper
from app.scrapers.boohoo import BoohooScraper
from app.scrapers.asos import AsosScraper
from app.scrapers.textilon import TextilonScraper
from app.scrapers.lupo import LupoScraper
from app.scrapers.women_secret import WomenSecretScraper
from app.scrapers.lili_pink import LiliPinkScraper

# All 10 sources from the spec are now registered. Confidence level varies
# a lot by source -- see each module's docstring:
#   HIGH  (live-verified end to end): suburbia, old_navy
#   MEDIUM (live-verified with real data, some fields incomplete): c_and_a, asos
#   MEDIUM (architecture solid, built on real captured samples, not
#           re-verified after latest fix): hm, zara
#   LOW / UNVERIFIED (built defensively, needs a first real smoke test
#           before you trust the numbers): target, shein, boohoo, primark
#
# Every scraper here fails LOUD (raises ScraperError, reported in
# scrape_runs.error_message) instead of returning fabricated data -- a
# source showing 0 products or a "failed" status is expected and normal
# until you've smoke-tested and (if needed) fixed its selectors against
# the real live site.
SCRAPERS: dict[str, type] = {
    "suburbia": SuburbiaScraper,
    "hm": HMScraper,
    "zara": ZaraScraper,
    "c_and_a": CAndAScraper,
    "primark": PrimarkScraper,
    "target": TargetScraper,
    "old_navy": OldNavyScraper,
    "shein": SheinScraper,
    "boohoo": BoohooScraper,
    "asos": AsosScraper,
    "textilon": TextilonScraper,
    "lupo": LupoScraper,
    "women_secret": WomenSecretScraper,
    "lili_pink": LiliPinkScraper,
}


def get_scraper(source: str) -> BaseScraper:
    cls = SCRAPERS.get(source)
    if not cls:
        raise ValueError(
            f"No scraper registered for source='{source}'. "
            f"Available: {list(SCRAPERS.keys())}"
        )
    return cls()