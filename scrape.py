"""
scrape.py — sťahovanie a čistenie HTML stránok.

Čo tento súbor robí:
1. Načíta webové stránky zo sites.json.
2. Otvorí každú stránku cez Crawl4AI a počká na načítanie (networkidle).
3. Vyčistí HTML pomocou BeautifulSoup — odstráni skripty, štýly,
   obrázky a technický balast, pričom zachová text a odkazy.
4. Uloží vyčistené HTML do priečinka scrape_output.

Tento súbor sa bežne nespúšťa priamo. Spúšťa ho main.py.
Žiadne AI spracovanie, porovnávanie zmien ani WordPress sa tu nevykonáva.
"""

import asyncio
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


PROJECT_DIR = Path(__file__).resolve().parent
SITES_FILE = PROJECT_DIR / "sites.json"
OUTPUT_DIR = PROJECT_DIR / "scrape_output"


# ANSI farby pre čitateľnejší výpis v termináli.
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"


def log(message, color=Colors.RESET):
    print(f"{color}{message}{Colors.RESET}")


def load_sites():
    """Načíta a skontroluje zoznam webových stránok."""
    if not SITES_FILE.exists():
        raise FileNotFoundError(f"Konfiguračný súbor neexistuje: {SITES_FILE}")

    with SITES_FILE.open("r", encoding="utf-8") as file:
        sites = json.load(file)

    if not isinstance(sites, list) or not sites:
        raise ValueError("sites.json musí obsahovať neprázdny zoznam.")

    for site in sites:
        if not isinstance(site, dict) or not site.get("name") or not site.get("url"):
            raise ValueError("Každá stránka musí mať vyplnené 'name' a 'url'.")

    return sites


def make_filename(site):
    """Vytvorí bezpečný názov HTML súboru podľa slug alebo názvu webu."""
    slug = site.get("slug") or site["name"].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"{slug or 'website'}.html"


def clean_html(html):
    """Odstráni technický balast, ale zachová čitateľný obsah a odkazy."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all([
        "script", "style", "noscript", "svg", "canvas",
        "img", "picture", "video", "audio", "source", "track",
        "iframe", "object", "embed"
    ]):
        tag.decompose()

    for comment in soup.find_all(
        string=lambda value: isinstance(value, Comment)
    ):
        comment.extract()

    allowed_attributes = {"href", "title", "aria-label", "datetime"}

    for tag in soup.find_all(True):
        tag.attrs = {
            name: value
            for name, value in tag.attrs.items()
            if name in allowed_attributes
        }

    # Odstráni prázdne kontajnery, ale zachová tie, ktoré obsahujú odkazy.
    for tag in soup.find_all(["div", "span", "section", "article"]):
        if not tag.get_text(" ", strip=True) and not tag.find("a", href=True):
            tag.decompose()

    # Odstráni iba obalové HTML elementy, ich obsah zostane zachovaný.
    for tag in soup.find_all(["div", "span", "section", "article"]):
        tag.unwrap()

    # Odstráni prázdne odseky a odkazy bez textu a bez cieľovej adresy.
    for tag in soup.find_all(["p", "a"]):
        if not tag.get_text(" ", strip=True):
            if tag.name == "a" and tag.get("href"):
                continue
            tag.decompose()

    return soup.prettify()


async def scrape_site(crawler, site, run_config, index, total):
    """Stiahne, vyčistí a uloží HTML jednej webovej stránky."""
    name = site["name"]
    url = site["url"]
    output_file = OUTPUT_DIR / make_filename(site)

    log(f"\n[{index}/{total}] {name}", Colors.BOLD + Colors.CYAN)
    log(f"URL: {url}", Colors.GRAY)
    log("Načítavam stránku...", Colors.BLUE)

    try:
        result = await crawler.arun(url=url, config=run_config)

        if not result.success:
            log(f"NEÚSPECH: {result.error_message}", Colors.RED)
            return False

        html = result.html or result.cleaned_html
        if not html:
            log("NEÚSPECH: Stránka vrátila prázdne HTML.", Colors.RED)
            return False

        log("Čistím HTML pomocou BeautifulSoup...", Colors.BLUE)
        cleaned = clean_html(html)

        output_file.write_text(cleaned, encoding="utf-8")

        original_size = len(html.encode("utf-8"))
        cleaned_size = len(cleaned.encode("utf-8"))
        reduction = (1 - cleaned_size / original_size) * 100 if original_size else 0
        link_count = len(
            BeautifulSoup(cleaned, "html.parser").find_all("a", href=True)
        )

        log("✓ HTML úspešne uložené", Colors.GREEN)
        log(f"  Súbor: {output_file.relative_to(PROJECT_DIR)}")
        log(f"  Pôvodná veľkosť: {original_size:,} B")
        log(f"  Vyčistená veľkosť: {cleaned_size:,} B")
        log(f"  Zmenšenie: {reduction:.1f}%")
        log(f"  Zachované odkazy: {link_count}")

        return True

    except Exception as error:
        log(f"CHYBA pri spracovaní {name}: {error}", Colors.RED)
        return False


async def run_scraper():
    """Spustí scraping všetkých webových stránok uvedených v sites.json."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sites = load_sites()

    log("\n" + "=" * 58, Colors.BLUE)
    log("  SCRAPING — SŤAHOVANIE A ČISTENIE HTML", Colors.BOLD + Colors.BLUE)
    log("=" * 58, Colors.BLUE)
    log(f"Počet webových stránok: {len(sites)}")
    log(f"Výstupný priečinok: {OUTPUT_DIR}\n", Colors.GRAY)

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        wait_until="networkidle",
        page_timeout=60000,
    )

    successful = 0
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for index, site in enumerate(sites, start=1):
            if await scrape_site(crawler, site, run_config, index, len(sites)):
                successful += 1

    failed = len(sites) - successful
    log("\n" + "-" * 58, Colors.BLUE)
    log("SÚHRN SCRAPINGU", Colors.BOLD + Colors.BLUE)
    log(f"Úspešne spracované: {successful}/{len(sites)}", Colors.GREEN)
    if failed:
        log(f"Neúspešné: {failed}/{len(sites)}", Colors.RED)
    log(f"HTML súbory nájdeš v: {OUTPUT_DIR}", Colors.GRAY)
    log("-" * 58 + "\n", Colors.BLUE)

    return successful, failed
