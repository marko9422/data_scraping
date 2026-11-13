"""
ai_prepare.py — príprava obsahu, ktorý neskôr odošleme do AI.

Zatiaľ NEVYKONÁVA žiadne API volanie. Iba pripraví a farebne vypíše
system prompt a používateľský obsah, ktorý by sa odoslal do AI.

Testovacie súbory:
- scrape_output/stoos-hotels.html      (nový HTML)
- scrape_output/stoos-hotels-old.html  (starý HTML)

Správanie:
- Ak starý súbor neexistuje, pripraví celý nový HTML súbor.
- Ak starý súbor existuje, pripraví rozdiely podľa logiky compare.py:
  ADDED = zelené, nové riadky
  REMOVED = červené, riadky zo starého súboru, ktoré v novom chýbajú

Spustenie:
    python ai_prepare.py
"""

import json
from difflib import SequenceMatcher
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "scrape_output"
SITES_FILE = PROJECT_DIR / "sites.json"

NEW_FILE = OUTPUT_DIR / "stoos-hotels.html"
OLD_FILE = OUTPUT_DIR / "stoos-hotels-old.html"
SITE_SLUG = "stoos-hotels"


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GRAY = "\033[90m"


def log(message="", color=Colors.RESET):
    print(f"{color}{message}{Colors.RESET}")


# Prompt structure copied and adapted from pipeline.py on
# feature/incremental-job-detection. No AI client is initialized here.
SYSTEM_PROMPT = """
Extract current, specific job vacancies from the supplied website content.
Return ONLY valid JSON with this schema:
{
  "jobs": [
    {
      "title": "job title",
      "url": "absolute job URL",
      "employment_type": "",
      "description": ""
    }
  ]
}

Rules:
- Extract only actual, currently available job vacancies.
- Do not return navigation links, legal pages, cookie notices, or general pages.
- Do not invent facts or fill in details that are not supported by the supplied content.
- Resolve relative links against the website URL supplied in the user message.
- Employer name, employer slug, workplace address, and canton are supplied manually
  from sites.json. Never extract or return these fields from the HTML.
- Do not include employer, slug, address, location, or canton in the JSON response.
- If the input is marked FULL_PAGE, inspect the complete page for current vacancies.
- If the input contains ADDED and REMOVED sections:
  - ADDED means content present in the new HTML. Use this as the primary source
    when identifying new or changed job offers.
  - REMOVED means content present only in the old HTML. It is shown for comparison
    and context only. NEVER report a vacancy based only on REMOVED content.
  - A removed section does not automatically prove that a job has closed.
  - Do not treat technical HTML changes, formatting changes, or unrelated text
    as a new job vacancy.
- If no actual current vacancies can be identified, return an empty jobs array.
"""


def load_site_metadata():
    """Načíta všetky manuálne údaje o zamestnávateľovi zo sites.json."""
    if not SITES_FILE.exists():
        return {
            "name": "Stoos Hotels",
            "url": "https://stoos-hotels.ch/karriere/",
            "address": "",
            "canton": "",
        }

    sites = json.loads(SITES_FILE.read_text(encoding="utf-8"))
    for site in sites:
        if site.get("slug") == SITE_SLUG:
            return site

    return {
        "name": "Stoos Hotels",
        "url": "https://stoos-hotels.ch/karriere/",
        "address": "",
        "canton": "",
    }


def build_diff(old_text, new_text):
    """Vytvorí ADDED a REMOVED riadky rovnakou logikou ako compare.py."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    added = []
    removed = []

    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            for number, line in enumerate(
                old_lines[old_start:old_end], start=old_start + 1
            ):
                removed.append((number, line))

        if tag in ("replace", "insert"):
            for number, line in enumerate(
                new_lines[new_start:new_end], start=new_start + 1
            ):
                added.append((number, line))

    return added, removed, len(old_lines), len(new_lines)


def format_diff_section(title, items, marker):
    """Vytvorí textovú sekciu pre obsah určený AI."""
    if not items:
        return f"{title}\n(none)"

    lines = [title]
    lines.extend(f"{marker} [line {number}] {line}" for number, line in items)
    return "\n".join(lines)


def prepare_input():
    """Pripraví system prompt a user input bez odoslania do AI."""
    if not NEW_FILE.exists():
        raise FileNotFoundError(f"Nový HTML súbor neexistuje: {NEW_FILE}")

    new_html = NEW_FILE.read_text(encoding="utf-8")
    site = load_site_metadata()

    metadata = (
        f"Website URL: {site.get('url', '')}\n"
        f"Employer name (manual, do not extract): {site.get('name', 'Stoos Hotels')}\n"
        f"Employer slug (manual, do not extract): {site.get('slug', SITE_SLUG)}\n"
        f"Workplace address (manual, do not extract): {site.get('address') or 'Neznáme'}\n"
        f"Canton (manual, do not extract): {site.get('canton') or 'Neznáme'}\n"
        f"New HTML file: {NEW_FILE.name}\n"
        f"Old HTML file: {OLD_FILE.name}\n"
    )

    if not OLD_FILE.exists():
        mode = "FULL_PAGE"
        user_content = (
            f"{metadata}\n"
            "CHANGE MODE: FULL_PAGE\n"
            "The old HTML file does not exist. This is the first scan.\n"
            "Analyze the complete new HTML page below.\n\n"
            f"=== FULL_PAGE: NEW HTML ===\n{new_html}"
        )
        stats = {
            "mode": mode,
            "added": None,
            "removed": None,
            "old_lines": 0,
            "new_lines": len(new_html.splitlines()),
        }
        return user_content, stats

    old_html = OLD_FILE.read_text(encoding="utf-8")
    added, removed, old_count, new_count = build_diff(old_html, new_html)

    user_content = (
        f"{metadata}\n"
        "CHANGE MODE: DIFF\n"
        "Compare the old and new HTML content using the sections below.\n"
        "ADDED lines belong to the NEW HTML.\n"
        "REMOVED lines belong only to the OLD HTML.\n\n"
        f"{format_diff_section('=== ADDED: NEW CONTENT ===', added, '+')}\n\n"
        f"{format_diff_section('=== REMOVED: OLD CONTENT ===', removed, '-')}"
    )

    stats = {
        "mode": "DIFF",
        "added": len(added),
        "removed": len(removed),
        "old_lines": old_count,
        "new_lines": new_count,
        "added_items": added,
        "removed_items": removed,
    }
    return user_content, stats


def print_prepared_input(user_content, stats):
    """Farebne zobrazí pripravený AI prompt a presný používateľský vstup."""
    log("\n" + "=" * 76, Colors.BLUE)
    log("PRÍPRAVA VSTUPU PRE AI — TESTOVACÍ REŽIM", Colors.BOLD + Colors.BLUE)
    log("=" * 76, Colors.BLUE)
    log("AI API: NEPOUŽÍVA SA", Colors.YELLOW)
    log(f"Režim: {stats['mode']}", Colors.CYAN)

    if stats["mode"] == "FULL_PAGE":
        log(f"Nový HTML: {stats['new_lines']} riadkov", Colors.GREEN)
        log("Starý HTML: neexistuje — pripravuje sa celý nový súbor.", Colors.YELLOW)
    else:
        log(f"Starý HTML: {stats['old_lines']} riadkov", Colors.GRAY)
        log(f"Nový HTML:  {stats['new_lines']} riadkov", Colors.GRAY)
        log(f"ADDED:      {stats['added']} riadkov", Colors.GREEN)
        log(f"REMOVED:    {stats['removed']} riadkov", Colors.RED)

    log("\n" + "-" * 76, Colors.CYAN)
    log("SYSTEM PROMPT — INŠTRUKCIE PRE AI", Colors.BOLD + Colors.CYAN)
    log("-" * 76, Colors.CYAN)
    print(SYSTEM_PROMPT.strip())

    log("\n" + "-" * 76, Colors.CYAN)
    log("USER INPUT — PRESNÝ OBSAH PRIPRAVENÝ PRE AI", Colors.BOLD + Colors.CYAN)
    log("-" * 76, Colors.CYAN)

    if stats["mode"] == "FULL_PAGE":
        print(user_content)
    else:
        sections = user_content.split("\n\n=== ADDED: NEW CONTENT ===\n", 1)
        print(sections[0])

        log("\n=== ADDED: NEW CONTENT ===", Colors.GREEN)
        if stats["added_items"]:
            for number, line in stats["added_items"]:
                log(f"+ [line {number}] {line}", Colors.GREEN)
        else:
            log("(none)", Colors.GRAY)

        log("\n=== REMOVED: OLD CONTENT ===", Colors.RED)
        if stats["removed_items"]:
            for number, line in stats["removed_items"]:
                log(f"- [line {number}] {line}", Colors.RED)
        else:
            log("(none)", Colors.GRAY)

    log("\n" + "=" * 76, Colors.BLUE)
    log("KONIEC — NIČ NEBOLO ODOSLANÉ DO AI", Colors.BOLD + Colors.YELLOW)
    log("=" * 76 + "\n", Colors.BLUE)


def main():
    try:
        user_content, stats = prepare_input()
        print_prepared_input(user_content, stats)
    except FileNotFoundError as error:
        log(f"CHYBA: {error}", Colors.RED)
        raise SystemExit(1)
    except (OSError, json.JSONDecodeError) as error:
        log(f"CHYBA pri čítaní súborov alebo konfigurácie: {error}", Colors.RED)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
