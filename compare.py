"""
compare.py — porovnávanie starého a nového HTML súboru.

Predvolené súbory:
- scrape_output/stoos-hotel.html      (nový HTML)
- scrape_output/stoos-hotel-old.html  (starý HTML)

Vypíše:
1. Riadky pridané v novom súbore.
2. Riadky odstránené oproti starému súboru.
3. Súhrn počtu pridaných a odstránených riadkov.

Spustenie:
    python compare.py

Voliteľne možno zadať vlastné názvy súborov:
    python compare.py novy.html stary.html
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


def compare_files(new_file, old_file):
    """Porovná dva textové súbory a vypíše pridané a odstránené riadky."""
    if not new_file.exists():
        log(f"CHYBA: Nový súbor neexistuje: {new_file}", Colors.RED)
        return False

    if not old_file.exists():
        log(f"CHYBA: Starý súbor neexistuje: {old_file}", Colors.RED)
        return False

    new_lines = new_file.read_text(encoding="utf-8").splitlines()
    old_lines = old_file.read_text(encoding="utf-8").splitlines()

    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)

    added = []
    removed = []

    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            for line_number, line in enumerate(
                old_lines[old_start:old_end], start=old_start + 1
            ):
                removed.append((line_number, line))

        if tag in ("replace", "insert"):
            for line_number, line in enumerate(
                new_lines[new_start:new_end], start=new_start + 1
            ):
                added.append((line_number, line))

    log("\n" + "=" * 70, Colors.BLUE)
    log("POROVNANIE HTML SÚBOROV", Colors.BOLD + Colors.BLUE)
    log("=" * 70, Colors.BLUE)
    log(f"NOVÝ súbor:  {new_file.name}", Colors.GREEN)
    log(f"STARÝ súbor: {old_file.name}", Colors.YELLOW)

    log("\n" + "-" * 70, Colors.GREEN)
    log(f"PRIDANÉ V NOVOM SÚBORE: {len(added)} riadkov", Colors.BOLD + Colors.GREEN)
    log("-" * 70, Colors.GREEN)

    if added:
        for line_number, line in added:
            log(f"+ [{line_number}] {line}", Colors.GREEN)
    else:
        log("Žiadne pridané riadky.", Colors.GRAY)

    log("\n" + "-" * 70, Colors.RED)
    log(f"ODSTRÁNENÉ OPROTI STARÉMU SÚBORU: {len(removed)} riadkov", Colors.BOLD + Colors.RED)
    log("-" * 70, Colors.RED)

    if removed:
        for line_number, line in removed:
            log(f"- [{line_number}] {line}", Colors.RED)
    else:
        log("Žiadne odstránené riadky.", Colors.GRAY)

    log("\n" + "=" * 70, Colors.BLUE)
    log("SÚHRN", Colors.BOLD + Colors.BLUE)
    log(f"Pridané riadky:     {len(added)}", Colors.GREEN)
    log(f"Odstránené riadky:  {len(removed)}", Colors.RED)
    log(f"Starý súbor:        {len(old_lines)} riadkov")
    log(f"Nový súbor:         {len(new_lines)} riadkov")
    log("=" * 70 + "\n", Colors.BLUE)

    return True


def main():
    """Načíta názvy súborov z argumentov alebo použije predvolené názvy."""
    if len(sys.argv) > 3:
        log("Použitie: python compare.py [novy_subor.html] [stary_subor.html]", Colors.YELLOW)
        raise SystemExit(2)

    new_name = sys.argv[1] if len(sys.argv) >= 2 else "stoos-hotel.html"
    old_name = sys.argv[2] if len(sys.argv) >= 3 else "stoos-hotel-old.html"

    new_file = OUTPUT_DIR / new_name
    old_file = OUTPUT_DIR / old_name

    if not compare_files(new_file, old_file):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
