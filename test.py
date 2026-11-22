"""
test.py — samostatné testovanie porovnávania HTML a Meta AI.

Spustenie:
    python test.py           # porovnanie + Meta AI
    python test.py --no-ai   # iba porovnanie, bez API volania

Používa iba:
    scrape_output/test.html
    scrape_output/test-old.html

Tento skript nemení HTML súbory, nespúšťa scraping a nikdy nevolá WordPress API.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from compare import compare_files, Colors, log
from ai_prepare import META_MODEL, parse_json, print_token_usage

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "scrape_output"
NEW_FILE = OUTPUT_DIR / "test.html"
OLD_FILE = OUTPUT_DIR / "test-old.html"

SYSTEM_PROMPT = """
Compare added and removed HTML evidence to identify changes in job vacancies.
Return ONLY valid JSON in this format:
{
  "changes": [
    {
      "action": "create",
      "job_title": "job title",
      "job_url": "job URL as shown in the HTML",
      "employment_type": "employment type, if available",
      "job_description": "description, if available"
    },
    {
      "action": "delete",
      "job_title": "job title",
      "job_url": "job URL as shown in the HTML"
    }
  ]
}

Rules:
- ADDED content exists in the new HTML only and can indicate a new or changed vacancy.
- REMOVED content exists in the old HTML only and can indicate a vacancy that disappeared.
- ADDED only = possible create; REMOVED only = possible delete.
- If the same vacancy appears on both sides, ignore it. Match by URL first, then by a clear job title.
- Analyze all changed lines and use surrounding lines to reconstruct split titles and links.
- Ignore formatting, navigation, tracking, cookie notices and unrelated page changes.
- Never invent a job, title, URL, employment type or description.
- Keep relative URLs exactly as they appear. There is no source URL in this test mode.
- If there is no clear evidence of a job vacancy change, return {"changes": []}.
"""


def build_ai_input(diff):
    """Build the exact user content sent to Meta AI from the HTML diff."""
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
        "Both ADDED and REMOVED sections are important.\n\n"
        f"{section('=== ADDED: PRESENT IN NEW HTML ===', added, '+')}\n\n"
        f"{section('=== REMOVED: PRESENT IN OLD HTML ===', removed, '-')}"
    )


def call_meta_ai(user_content):
    """Send the test diff to Meta AI. No WordPress integration is used."""
    api_key = os.getenv("META_API_KEY")
    if not api_key:
        raise RuntimeError("META_API_KEY missing from .env")

    client = OpenAI(
        base_url="https://api.meta.ai/v1",
        api_key=api_key,
    )
    return client.chat.completions.create(
        model=META_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        extra_body={"prompt_cache_key": "data-scraping-test-diff-v1"},
        temperature=0,
        reasoning_effort="minimal",
        max_tokens=2000,
    )


def main():
    no_ai = len(sys.argv) == 2 and sys.argv[1] == "--no-ai"
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and not no_ai):
        log("Použitie: python test.py [--no-ai]", Colors.YELLOW)
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

        user_content = build_ai_input(diff)

        log("\n" + "=" * 78, Colors.BLUE)
        log("META AI ANALÝZA", Colors.BOLD + Colors.CYAN)
        log(f"Model: {META_MODEL}", Colors.CYAN)
        log("=" * 78, Colors.BLUE)
        log("\n--- SYSTEM PROMPT ---", Colors.CYAN)
        print(SYSTEM_PROMPT.strip())
        log("\n--- USER CONTENT (odosielaný obsah) ---", Colors.CYAN)
        print(user_content)

        log("\nOdosielam zmeny do Meta AI...", Colors.YELLOW)
        response = call_meta_ai(user_content)
        print_token_usage(getattr(response, "usage", None))

        raw_output = response.choices[0].message.content or ""
        log("\n--- RAW AI OUTPUT ---", Colors.CYAN)
        print(raw_output)

        result = parse_json(raw_output)
        if not isinstance(result, dict) or not isinstance(result.get("changes"), list):
            raise ValueError('AI odpoveď musí obsahovať pole "changes".')

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
