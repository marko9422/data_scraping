"""
test.py — samostatné testovanie porovnávania HTML a Meta AI.

Spustenie:
    python test.py           # porovnanie + Meta AI + finálny JSON
    python test.py --no-ai   # iba porovnanie, bez API volania

Používa iba:
    scrape_output/test.html
    scrape_output/test-old.html

Tento skript nemení HTML súbory, nespúšťa scraping a nikdy nevolá WordPress API.
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from compare import compare_files, Colors, log
from ai_prepare import (
    SYSTEM_PROMPT,
    META_MODEL,
    build_acf_json,
    load_site,
    parse_json,
    print_token_usage,
    call_ai,
)

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "scrape_output"
NEW_FILE = OUTPUT_DIR / "test.html"
OLD_FILE = OUTPUT_DIR / "test-old.html"

# Employer used to generate job_id and enrich the final JSON.
# Change this constant when testing HTML files from another employer.
TEST_EMPLOYER_SLUG = "stoos-hotels"


def build_ai_input(diff, site):
    """Build the test diff request, including employer URL for relative links."""
    added = diff["added"]
    removed = diff["removed"]

    def section(title, rows, marker):
        if not rows:
            return f"{title}\n(none)"
        lines = [title]
        lines.extend(
            f"{marker} [line {line_number}] {line}"
            for line_number, line in rows
        )
        return "\n".join(lines)

    return (
        "INPUT MODE: DIFF\n"
        "Analyze the changes between the new and old HTML.\n"
        "Both ADDED and REMOVED sections are important.\n"
        f"SOURCE_URL: {site.get('url', '')}\n\n"
        f"{section('=== ADDED: PRESENT IN NEW HTML ===', added, '+')}\n\n"
        f"{section('=== REMOVED: PRESENT IN OLD HTML ===', removed, '-')}"
    )


def main():
    args = sys.argv[1:]
    if args not in ([], ["--no-ai"]):
        log("Použitie: python test.py [--no-ai]", Colors.YELLOW)
        raise SystemExit(2)

    no_ai = args == ["--no-ai"]

    try:
        log("\n" + "=" * 78, Colors.BLUE)
        log("HTML TEST WORKFLOW", Colors.BOLD + Colors.BLUE)
        log(f"Nový súbor: {NEW_FILE}", Colors.GREEN)
        log(f"Starý súbor: {OLD_FILE}", Colors.YELLOW)
        log("=" * 78, Colors.BLUE)

        # Always compare the two fixed test snapshots.
        diff = compare_files(NEW_FILE, OLD_FILE)

        if no_ai:
            log("Režim --no-ai: Meta AI sa nespúšťa.", Colors.YELLOW)
            log("WordPress API: NOT CALLED.", Colors.YELLOW)
            return

        if not diff["added"] and not diff["removed"]:
            log("HTML súbory sú identické. Meta AI sa nevolá.", Colors.GREEN)
            log('Výsledok: {"changes": []}', Colors.GREEN)
            log("WordPress API: NOT CALLED.", Colors.YELLOW)
            return

        # The slug is configured above, so the command stays parameter-free.
        site = load_site(TEST_EMPLOYER_SLUG)
        user_content = build_ai_input(diff, site)

        log("\n" + "=" * 78, Colors.BLUE)
        log("META AI ANALÝZA", Colors.BOLD + Colors.CYAN)
        log(f"Zamestnávateľ: {site.get('name')} | Slug: {TEST_EMPLOYER_SLUG}", Colors.CYAN)
        log(f"Model: {META_MODEL}", Colors.CYAN)
        log("=" * 78, Colors.BLUE)
        log("\n--- SYSTEM PROMPT ---", Colors.CYAN)
        print(SYSTEM_PROMPT.strip())
        log("\n--- USER CONTENT (odosielaný obsah) ---", Colors.CYAN)
        print(user_content)

        log("\nOdosielam zmeny do Meta AI...", Colors.YELLOW)
        response = call_ai(user_content)
        print_token_usage(getattr(response, "usage", None))

        raw_output = response.choices[0].message.content or ""
        log("\n--- RAW AI OUTPUT ---", Colors.CYAN)
        print(raw_output)

        # Same final JSON builder as the main ai_prepare.py workflow.
        result = build_acf_json(parse_json(raw_output), site)

        log("\n--- FINAL JSON ---", Colors.BOLD + Colors.GREEN)
        print(json.dumps(result, ensure_ascii=False, indent=2))

        creates = sum(1 for item in result["changes"] if item.get("action") == "create")
        deletes = sum(1 for item in result["changes"] if item.get("action") == "delete")
        log(f"\nNové pracovné ponuky: {creates}", Colors.GREEN)
        log(f"Odstránené pracovné ponuky: {deletes}", Colors.RED)
        log("WordPress API: NOT CALLED. Nič nebolo odoslané do WordPressu.", Colors.YELLOW)

    except KeyboardInterrupt:
        log("\nTest bol prerušený používateľom.", Colors.YELLOW)
        raise SystemExit(130)
    except Exception as error:
        log(f"\nCHYBA: {error}", Colors.RED)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
