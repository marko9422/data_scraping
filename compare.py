"""
compare.py — porovnávanie starého a nového HTML.

Funkcia get_diff() vracia štruktúrovaný diff pre ďalšie moduly.
Spustenie z terminálu stále vypíše pridané a odstránené riadky.
"""

import sys
from pathlib import Path
from difflib import SequenceMatcher


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "scrape_output"


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GRAY = "\033[90m"


def log(message, color=Colors.RESET):
    print(f"{color}{message}{Colors.RESET}")


def get_diff(new_file, old_file):
    """Vráti pridané/odstránené riadky a štatistiky; pri chybe vyhodí výnimku."""
    if not new_file.exists():
        raise FileNotFoundError(f"Nový HTML súbor neexistuje: {new_file}")
    if not old_file.exists():
        raise FileNotFoundError(f"Starý HTML súbor neexistuje: {old_file}")

    new_lines = new_file.read_text(encoding="utf-8").splitlines()
    old_lines = old_file.read_text(encoding="utf-8").splitlines()
    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)

    added, removed = [], []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(
                (line_number, line)
                for line_number, line in enumerate(old_lines[old_start:old_end], start=old_start + 1)
            )
        if tag in ("replace", "insert"):
            added.extend(
                (line_number, line)
                for line_number, line in enumerate(new_lines[new_start:new_end], start=new_start + 1)
            )

    return {
        "added": added,
        "removed": removed,
        "old_lines": len(old_lines),
        "new_lines": len(new_lines),
    }


def compare_files(new_file, old_file):
    """Porovná súbory, vypíše diff a vráti jeho štruktúrované dáta."""
    diff = get_diff(new_file, old_file)

    log("\n" + "=" * 70, Colors.BLUE)
    log("POROVNANIE HTML SÚBOROV", Colors.BOLD + Colors.BLUE)
    log("=" * 70, Colors.BLUE)
    log(f"NOVÝ súbor:  {new_file.name}", Colors.GREEN)
    log(f"STARÝ súbor: {old_file.name}", Colors.YELLOW)

    log("\n" + "-" * 70, Colors.GREEN)
    log(f"PRIDANÉ V NOVOM SÚBORE: {len(diff['added'])} riadkov", Colors.BOLD + Colors.GREEN)
    log("-" * 70, Colors.GREEN)
    if diff["added"]:
        for line_number, line in diff["added"]:
            log(f"+ [{line_number}] {line}", Colors.GREEN)
    else:
        log("Žiadne pridané riadky.", Colors.GRAY)

    log("\n" + "-" * 70, Colors.RED)
    log(f"ODSTRÁNENÉ OPROTI STARÉMU SÚBORU: {len(diff['removed'])} riadkov", Colors.BOLD + Colors.RED)
    log("-" * 70, Colors.RED)
    if diff["removed"]:
        for line_number, line in diff["removed"]:
            log(f"- [{line_number}] {line}", Colors.RED)
    else:
        log("Žiadne odstránené riadky.", Colors.GRAY)

    log("\n" + "=" * 70, Colors.BLUE)
    log("SÚHRN", Colors.BOLD + Colors.BLUE)
    log(f"Pridané riadky:     {len(diff['added'])}", Colors.GREEN)
    log(f"Odstránené riadky:  {len(diff['removed'])}", Colors.RED)
    log(f"Starý súbor:        {diff['old_lines']} riadkov")
    log(f"Nový súbor:         {diff['new_lines']} riadkov")
    log("=" * 70 + "\n", Colors.BLUE)
    return diff


def main():
    if len(sys.argv) > 3:
        log("Použitie: python compare.py [novy_subor.html] [stary_subor.html]", Colors.YELLOW)
        raise SystemExit(2)

    new_name = sys.argv[1] if len(sys.argv) >= 2 else "stoos-hotels.html"
    old_name = sys.argv[2] if len(sys.argv) >= 3 else "stoos-hotels-old.html"
    compare_files(OUTPUT_DIR / new_name, OUTPUT_DIR / old_name)


if __name__ == "__main__":
    main()
