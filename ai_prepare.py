"""
Meta AI job extraction and ACF JSON preview. No WordPress API calls.
"""

import json
import os
import re
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "scrape_output"
SITES_FILE = ROOT / "sites.json"
NEW_FILE = OUTPUT / "stoos-hotels.html"
OLD_FILE = OUTPUT / "stoos-hotels-old.html"
SITE_SLUG = "stoos-hotels"
META_API_KEY = os.getenv("META_API_KEY")
META_MODEL = os.getenv("META_MODEL", "muse-spark-1.3-contributor")
UNAVAILABLE = "Unavailable"


class Colors:
    RESET = "\033[0m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BOLD = "\033[1m"


def log(message="", color=Colors.RESET):
    print(f"{color}{message}{Colors.RESET}")


SYSTEM_PROMPT = """
Extract current, specific job vacancies from the supplied website content.
Return ONLY valid JSON, without Markdown fences or explanations, using this schema:

{
  "jobs": [
    {
      "job_title": "Job title",
      "employer_name": "Employer name",
      "job_location": "Workplace address",
      "employment_type": "Employment type",
      "job_description": "Job description",
      "job_url": "Absolute job URL",
      "source_url": "Source website URL",
      "scraped_at": "YYYY-MM-DD",
      "canton": "Swiss canton",
      "scope": "Employer scope/category",
      "employer_slug": "Employer slug"
    }
  ]
}

The user message provides trusted employer metadata from sites.json.
Copy these fields exactly from that metadata: employer_name, job_location,
source_url, canton, scope, employer_slug. Do not infer or modify them.
Copy scraped_at from the supplied metadata too.
You extract only job_title, employment_type, job_description, and job_url.
If any AI-owned field is unknown, use exactly "Unavailable" (English).
Do not invent facts. job_url must be absolute; resolve relative links against source_url.
Extract only actual current vacancies, not navigation or general pages.
Return one object per distinct vacancy, without duplicates.
If there are no current vacancies, return {"jobs": []}.

For FULL_PAGE input, inspect the complete new HTML.
For DIFF input, ADDED lines belong to the new HTML and REMOVED lines only to the old HTML.
Use ADDED as primary evidence. Never report a vacancy based only on REMOVED content.
A removed line alone does not prove that a vacancy has closed.
Ignore formatting and unrelated technical HTML changes.
"""


def load_site():
    if not SITES_FILE.exists():
        raise FileNotFoundError(f"Missing config: {SITES_FILE}")
    sites = json.loads(SITES_FILE.read_text(encoding="utf-8"))
    for site in sites:
        if site.get("slug") == SITE_SLUG:
            return site
    raise ValueError(f"Employer slug not found in sites.json: {SITE_SLUG}")


def value_or_unavailable(value):
    return str(value).strip() if value is not None and str(value).strip() else UNAVAILABLE


def make_diff(old_text, new_text):
    old_lines, new_lines = old_text.splitlines(), new_text.splitlines()
    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    added, removed = [], []
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend((i, line) for i, line in enumerate(old_lines[a:b], a + 1))
        if tag in ("replace", "insert"):
            added.extend((i, line) for i, line in enumerate(new_lines[c:d], c + 1))
    return added, removed, len(old_lines), len(new_lines)


def diff_section(title, rows, marker):
    if not rows:
        return title + "\n(none)"
    return "\n".join([title] + [f"{marker} [line {n}] {line}" for n, line in rows])


def prepare_input(site):
    if not NEW_FILE.exists():
        raise FileNotFoundError(f"New HTML file not found: {NEW_FILE}")
    new_html = NEW_FILE.read_text(encoding="utf-8")
    source_url = value_or_unavailable(site.get("url"))
    metadata = {
        "employer_name": value_or_unavailable(site.get("name")),
        "job_location": value_or_unavailable(site.get("address")),
        "source_url": source_url,
        "canton": value_or_unavailable(site.get("canton")),
        "scope": value_or_unavailable(site.get("scope")),
        "employer_slug": value_or_unavailable(site.get("slug")),
        "scraped_at": date.today().isoformat(),
    }
    meta_json = json.dumps(metadata, ensure_ascii=False, indent=2)

    if not OLD_FILE.exists():
        content = (
            "INPUT MODE: FULL_PAGE\n"
            "First scan: inspect the complete current HTML.\n\n"
            f"EMPLOYER METADATA (copy exactly):\n{meta_json}\n\n"
            f"=== FULL_PAGE: NEW HTML ({NEW_FILE.name}) ===\n{new_html}"
        )
        return content, {"mode": "FULL_PAGE", "new_lines": len(new_html.splitlines())}

    old_html = OLD_FILE.read_text(encoding="utf-8")
    added, removed, old_count, new_count = make_diff(old_html, new_html)
    content = (
        "INPUT MODE: DIFF\n"
        "Extract current vacancies from new content; removed content is context only.\n\n"
        f"EMPLOYER METADATA (copy exactly):\n{meta_json}\n\n"
        f"{diff_section('=== ADDED: NEW CONTENT ===', added, '+')}\n\n"
        f"{diff_section('=== REMOVED: OLD CONTENT ===', removed, '-')}"
    )
    return content, {
        "mode": "DIFF", "added": len(added), "removed": len(removed),
        "old_lines": old_count, "new_lines": new_count,
    }


def parse_json(raw):
    text = raw.strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = re.sub(r"^" + re.escape(fence) + r"(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*" + re.escape(fence) + r"$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start:end + 1])


def build_acf_json(data, site):
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError('AI response must contain a "jobs" array.')

    source_url = value_or_unavailable(site.get("url"))
    manual = {
        "employer_name": value_or_unavailable(site.get("name")),
        "job_location": value_or_unavailable(site.get("address")),
        "source_url": source_url,
        "canton": value_or_unavailable(site.get("canton")),
        "scope": value_or_unavailable(site.get("scope")),
        "employer_slug": value_or_unavailable(site.get("slug")),
    }

    jobs = []
    for number, item in enumerate(data["jobs"], 1):
        if not isinstance(item, dict):
            raise ValueError(f"Job #{number} is not an object.")
        url = value_or_unavailable(item.get("job_url"))
        if url != UNAVAILABLE:
            url = urljoin(source_url, url)

        # Metadata fields are overwritten locally from sites.json,
        # so the AI cannot accidentally change these trusted values.
        jobs.append({
            "job_title": value_or_unavailable(item.get("job_title")),
            **manual,
            "employment_type": value_or_unavailable(item.get("employment_type")),
            "job_description": value_or_unavailable(item.get("job_description")),
            "job_url": url,
            "scraped_at": date.today().isoformat(),
        })
    return {"jobs": jobs}


def print_token_usage(usage):
    if usage is None:
        log("Token usage unavailable from API.", Colors.YELLOW)
        return
    input_tokens = getattr(usage, "prompt_tokens", None)
    if input_tokens is None:
        input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    if output_tokens is None:
        output_tokens = getattr(usage, "output_tokens", None)
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", None) if details else None
    log("\nTOKEN USAGE", Colors.BOLD + Colors.CYAN)
    log(f"Input tokens:  {input_tokens if input_tokens is not None else UNAVAILABLE}")
    log(f"Output tokens: {output_tokens if output_tokens is not None else UNAVAILABLE}")
    if cached is not None:
        log(f"Cached input:  {cached}")
    if input_tokens is not None and output_tokens is not None:
        log(f"Total tokens:  {input_tokens + output_tokens}")


def call_ai(user_content):
    if not META_API_KEY:
        raise RuntimeError("META_API_KEY missing from .env")
    client = OpenAI(base_url="https://api.meta.ai/v1", api_key=META_API_KEY)
    return client.chat.completions.create(
        model=META_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        max_tokens=4000,
    )


def main():
    try:
        site = load_site()
        user_content, stats = prepare_input(site)

        log("=" * 78, Colors.BLUE)
        log("META AI REQUEST — EXACT PROMPT AND PAYLOAD", Colors.BOLD + Colors.BLUE)
        log(f"Model: {META_MODEL} | Mode: {stats['mode']}", Colors.CYAN)
        if stats["mode"] == "DIFF":
            log(f"ADDED: {stats['added']} lines | REMOVED: {stats['removed']} lines")
        log("\n--- SYSTEM PROMPT ---", Colors.CYAN)
        print(SYSTEM_PROMPT.strip())
        log("\n--- USER CONTENT (exact request payload) ---", Colors.CYAN)
        print(user_content)

        log("\nCalling Meta AI...", Colors.YELLOW)
        response = call_ai(user_content)
        print_token_usage(getattr(response, "usage", None))

        raw = response.choices[0].message.content or ""
        log("\n--- RAW AI OUTPUT ---", Colors.CYAN)
        print(raw)

        final_data = build_acf_json(parse_json(raw), site)
        log("\n--- FINAL JSON: COMPLETE ACF FIELDS ---", Colors.BOLD + Colors.GREEN)
        print(json.dumps(final_data, ensure_ascii=False, indent=2))
        log(f"\nJobs found: {len(final_data['jobs'])}", Colors.GREEN)
        log("WordPress API: NOT CALLED. Nothing was sent to WordPress.", Colors.YELLOW)

    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        log(f"ERROR: {error}", Colors.RED)
        raise SystemExit(1)
    except Exception as error:
        log(f"AI/API error: {error}", Colors.RED)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
