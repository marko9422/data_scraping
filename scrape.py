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
import shutil
import sys
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


def make_old_filename(site):
    """Vytvorí názov záložného HTML snapshotu."""
    return f"{Path(make_filename(site)).stem}-old.html"


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

        html = result.html if result.html is not None else result.cleaned_html
        if html is None:
            html = ""

        if not html.strip():
            log("UPOZORNENIE: Stránka vrátila prázdne HTML. Uložím prázdny snapshot; AI dostane pokyn nevyvodzovať žiadne pracovné ponuky.", Colors.YELLOW)

        log("Čistím HTML pomocou BeautifulSoup...", Colors.BLUE)
        cleaned = clean_html(html)

        # Pred prepísaním aktuálneho HTML zachovaj predchádzajúci snapshot.
        if output_file.exists():
            old_file = OUTPUT_DIR / make_old_filename(site)
            shutil.copy2(output_file, old_file)
            log(f"Predchádzajúci HTML snapshot uložený: {old_file.name}", Colors.YELLOW)

        output_file.write_text(cleaned, encoding="utf-8")

        log("✓ HTML úspešne uložené", Colors.GREEN)
        log(f"  Súbor: {output_file.relative_to(PROJECT_DIR)}")

        return True

    except Exception as error:
        log(f"CHYBA pri spracovaní {name}: {error}", Colors.RED)
        return False


async def run_scraper(site_slug=None):
    """Scrapuje jednu stránku podľa slug alebo všetky stránky zo sites.json."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sites = load_sites()

    if site_slug:
        sites = [site for site in sites if site.get("slug") == site_slug]
        if not sites:
            available = ", ".join(
                str(site.get("slug")) for site in load_sites() if site.get("slug")
            )
            raise ValueError(
                f"Slug '{site_slug}' sa nenašiel v sites.json. Dostupné slugy: {available}"
            )

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


def main():
    """CLI: python scrape.py [slug]. Bez slug spracuje všetky weby."""
    if len(sys.argv) > 2:
        log("Použitie: python scrape.py [slug]", Colors.YELLOW)
        raise SystemExit(2)

    site_slug = sys.argv[1] if len(sys.argv) == 2 else None

    try:
        successful, failed = asyncio.run(run_scraper(site_slug))
        if failed:
            raise SystemExit(1)
    except KeyboardInterrupt:
        log("\\nScraping bol prerušený používateľom.", Colors.YELLOW)
        raise SystemExit(130)
    except Exception as error:
        log(f"\\nFATAL ERROR: {error}", Colors.RED)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
