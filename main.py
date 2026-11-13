"""
main.py — hlavný vstupný bod projektu.

Spúšťa scraper z modulu scrape.py.
Všetka logika sťahovania a čistenia HTML je oddelená v scrape.py.
"""

import asyncio

from scrape import run_scraper, Colors, log


def main():
    """Spustí celý scraping proces."""
    try:
        successful, failed = asyncio.run(run_scraper())
        if failed:
            raise SystemExit(1)
    except KeyboardInterrupt:
        log("\nScraping bol prerušený používateľom.", Colors.YELLOW)
        raise SystemExit(130)
    except Exception as error:
        log(f"\nFATAL ERROR: {error}", Colors.RED)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
