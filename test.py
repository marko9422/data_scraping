"""
test.py — samostatné testovanie porovnávania HTML a Meta AI.

Spustenie:
    python test.py stoos-hotels            # porovnanie + Meta AI + finálny JSON
    python test.py stoos-hotels --no-ai    # iba porovnanie, bez API volania
    python test.py --no-ai                 # porovnanie bez AI a bez employer metadata

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
    no_ai = "--no-ai" in args
    positional = [arg for arg in args if arg != "--no-ai"]

    if len(positional) > 1 or (not no_ai and len(positional) != 1):
        log("Použitie: python test.py <employer-slug> [--no-ai]", Colors.YELLOW)
        log("Príklad: python test.py stoos-hotels", Colors.YELLOW)
        raise SystemExit(2)

    site = None
    if positional:
        try:
            site = load_site(positional[0])
        except ValueError as error:
            log(str(error), Colors.RED)
            raise SystemExit(2)

    try:
        log("\n" + "=" * 78, Colors.BLUE)
        log("HTML TEST WORKFLOW", Colors.BOLD + Colors.BLUE)
        log(f"Nový súbor: {NEW_FILE}", Colors.GREEN)
        log(f"Starý súbor: {OLD_FILE}", Colors.YELLOW)
        log("=" * 78, Colors.BLUE)

        # Print the diff and retain its structured data for the AI request.
        diff = compare_files(NEW_FILE, OLD_FILE)

        if no_ai:
            log("Režim --no-ai: Meta AI sa nespúšťa.", Colors.YELLOW)
            log("WordPress API: NOT CALLED.", Colors.YELLOW)
            return

        if not diff["added"] and not diff["removed"]:
            log("HTML súbory sú identické. Meta AI sa nevolá.", Colors.GREEN)
            log("Výsledok: {\"changes\": []}", Colors.GREEN)
            log("WordPress API: NOT CALLED.", Colors.YELLOW)
            return

        user_content = build_ai_input(diff, site)

        log("\n" + "=" * 78, Colors.BLUE)
        log("META AI ANALÝZA", Colors.BOLD + Colors.CYAN)
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

        result = build_acf_json(parse_json(raw_output), site)

        log("\n--- FINAL JSON ---", Colors.BOLD + Colors.GREEN)
        print(json.dumps(result, ensure_ascii=False, indent=2))

        creates = sum(
            1 for item in result["changes"]
            if isinstance(item, dict) and item.get("action") == "create"
        )
        deletes = sum(
            1 for item in result["changes"]
            if isinstance(item, dict) and item.get("action") == "delete"
        )
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
