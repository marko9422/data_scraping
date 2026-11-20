"""
main.py — kompletný workflow pre jedného zamestnávateľa.

Spustenie:
    python main.py <slug>

Poradie:
1. Scrape + BeautifulSoup; pred prepísaním uloží predchádzajúci snapshot.
2. Porovnanie nového a starého HTML.
3. Meta AI analýza diffu alebo prvého HTML snapshotu.
"""

import asyncio
import sys
from pathlib import Path

from scrape import run_scraper, load_sites, make_filename, make_old_filename, Colors, log
from compare import compare_files
from ai_prepare import run_ai_pipeline

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "scrape_output"


def find_site(site_slug):
    for site in load_sites():
        if site.get("slug") == site_slug:
            return site
    available = ", ".join(
        site.get("slug", "") for site in load_sites() if site.get("slug")
    )
    raise ValueError(
        f"Slug '{site_slug}' sa nenašiel v sites.json. Dostupné slugy: {available}"
    )


def main():
    if len(sys.argv) != 2:
        log("Použitie: python main.py <slug>", Colors.YELLOW)
        raise SystemExit(2)

    site_slug = sys.argv[1]

    try:
        site = find_site(site_slug)
        new_file = OUTPUT_DIR / make_filename(site)
        old_file = OUTPUT_DIR / make_old_filename(site)

        # Zisti, či ide o prvé skenovanie ešte pred tým, ako scraper vytvorí backup.
        first_scan = not new_file.exists()

        log("\\n" + "=" * 78, Colors.BLUE)
        log(f"FULL JOB SCRAPING WORKFLOW — {site['name']}", Colors.BOLD + Colors.BLUE)
        log(f"Slug: {site_slug}", Colors.CYAN)
        log("=" * 78, Colors.BLUE)

        # KROK 1: stiahni stránku a vyčisti HTML.
        log("\\nKROK 1/3 — SCRAPING A ČISTENIE HTML", Colors.BOLD + Colors.CYAN)
        successful, failed = asyncio.run(run_scraper(site_slug))
        if failed or successful != 1:
            raise RuntimeError("Scraping zlyhal. Porovnávanie a AI sa nespustia.")

        if not new_file.exists():
            raise FileNotFoundError(f"Scraper nevytvoril očakávaný súbor: {new_file}")

        # KROK 2: pri existujúcom predchádzajúcom snapshot-e porovnaj HTML.
        diff = None
        if first_scan:
            log("\\nKROK 2/3 — PRVÉ SKENOVANIE", Colors.BOLD + Colors.CYAN)
            log("Predchádzajúci HTML snapshot neexistuje. Diff sa nedá vytvoriť.", Colors.YELLOW)
            log("Aktuálne HTML sa pošle AI ako FIRST_SCAN.", Colors.YELLOW)
        else:
            if not old_file.exists():
                raise FileNotFoundError(
                    f"Predchádzajúci snapshot chýba: {old_file}. "
                    "Aby sa nestratili zmeny, AI analýza sa zastavila."
                )
            log("\\nKROK 2/3 — POROVNANIE HTML", Colors.BOLD + Colors.CYAN)
            diff = compare_files(new_file, old_file)

        # KROK 3: AI dostane celý diff alebo kompletné HTML pri prvom skenovaní.
        log("\\nKROK 3/3 — META AI ANALÝZA", Colors.BOLD + Colors.CYAN)
        run_ai_pipeline(
            site_slug,
            new_file,
            old_file,
            first_scan=first_scan,
            diff=diff,
        )

        log("\\nWORKFLOW DOKONČENÝ", Colors.BOLD + Colors.GREEN)

    except KeyboardInterrupt:
        log("\\nWorkflow bol prerušený používateľom.", Colors.YELLOW)
        raise SystemExit(130)
    except Exception as error:
        log(f"\\nFATAL ERROR: {error}", Colors.RED)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
