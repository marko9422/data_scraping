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
Extract job vacancies from the supplied website content.
Return ONLY valid JSON using this schema:
{
  "jobs": [{"job_title":"...", "employer_name":"...", "job_location":"...", "employment_type":"...", "job_description":"...", "job_url":"...", "source_url":"...", "scraped_at":"YYYY-MM-DD", "canton":"...", "scope":"...", "employer_slug":"..."}],
  "removed_jobs": [{"job_title":"...", "job_url":"..."}]
}

Copy employer_name, job_location, source_url, canton, scope, employer_slug and scraped_at exactly from EMPLOYER METADATA for each item in jobs.
Extract job_title, employment_type, job_description and job_url for current jobs. Unknown values must be "Unavailable". Resolve relative URLs against source_url. Do not invent facts or include navigation links.

FULL_PAGE: extract all current vacancies into jobs and return removed_jobs as [].

DIFF:
- Extract actual current/new vacancies from ADDED into jobs.
- REMOVED belongs to the old page. If a clearly identifiable vacancy listing (job title and/or its job link) was removed, return it in removed_jobs.
- Never put a removed-only vacancy into jobs.
- removed_jobs contains only job_title and job_url; use "Unavailable" if unavailable.
- Ignore removed navigation links and unrelated HTML.
- A removed item is only a deletion candidate. The application verifies its URL against the complete new HTML before any future WordPress action.
Return empty arrays when there are no matching items.
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

def extract_removed_jobs(removed_rows, new_html, source_url):
    """Find removed vacancy anchors and verify their URLs are absent from new HTML."""
    from html import unescape

    removed_html = "\n".join(line for _, line in removed_rows)
    pattern = re.compile(r"""<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)
    found = {}
    for match in pattern.finditer(removed_html):
        raw_url, anchor_text = match.groups()
        absolute_url = urljoin(source_url, unescape(raw_url.strip()))
        if absolute_url in new_html or unescape(raw_url.strip()) in new_html:
            continue
        title = re.sub(r"<[^>]+>", " ", anchor_text)
        title = " ".join(unescape(title).split()) or UNAVAILABLE
        found[absolute_url] = {"job_title": title, "job_url": absolute_url}
    return list(found.values())



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
    removed_jobs = extract_removed_jobs(removed, new_html, source_url)
    return content, {
        "mode": "DIFF", "added": len(added), "removed": len(removed),
        "old_lines": old_count, "new_lines": new_count,
        "removed_jobs": removed_jobs,
        "has_meaningful_additions": any(line.strip() for _, line in added),
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
    removed_jobs = data.get("removed_jobs", [])
    if not isinstance(removed_jobs, list):
        raise ValueError('"removed_jobs" must be a list.')
    normalized_removed = []
    for item in removed_jobs:
        if not isinstance(item, dict):
            raise ValueError("Each removed job must be an object.")
        url = value_or_unavailable(item.get("job_url"))
        if url != UNAVAILABLE:
            url = urljoin(source_url, url)
        normalized_removed.append({
            "job_title": value_or_unavailable(item.get("job_title")),
            "job_url": url,
        })
    return {"jobs": jobs, "removed_jobs": normalized_removed}


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
            # Keep the unchanged system prompt first for Meta's automatic prefix cache.
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        # Stable across requests using this extraction prompt.
        extra_body={"prompt_cache_key": "data-scraping-job-extraction-v1"},
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

            # Skip identical snapshots: there is no new content for the model to inspect.
            if stats["added"] == 0 and stats["removed"] == 0:
                log("\nNo HTML changes detected. Meta AI was not called.", Colors.GREEN)
                log("No new or removed vacancies to process.", Colors.YELLOW)
                log("WordPress API: NOT CALLED.", Colors.YELLOW)
                return

            # Pure removals and whitespace changes need no AI request.
            if not stats["has_meaningful_additions"]:
                final_data = {"jobs": [], "removed_jobs": stats["removed_jobs"]}
                log("\nNo meaningful new content. Meta AI was not called.", Colors.GREEN)
                log("\n--- FINAL JSON ---", Colors.BOLD + Colors.GREEN)
                print(json.dumps(final_data, ensure_ascii=False, indent=2))
                log(f"Removed job candidates: {len(final_data['removed_jobs'])}", Colors.YELLOW)
                log("WordPress API: NOT CALLED.", Colors.YELLOW)
                return
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
        if stats["mode"] == "DIFF":
            final_data["removed_jobs"] = stats["removed_jobs"]
        log("\n--- FINAL JSON: JOBS AND REMOVAL CANDIDATES ---", Colors.BOLD + Colors.GREEN)
        print(json.dumps(final_data, ensure_ascii=False, indent=2))
        log(f"\nJobs found: {len(final_data['jobs'])}", Colors.GREEN)
        log(f"Removed job candidates: {len(final_data['removed_jobs'])}", Colors.YELLOW)
        log("WordPress API: NOT CALLED. Nothing was sent to WordPress.", Colors.YELLOW)

    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        log(f"ERROR: {error}", Colors.RED)
        raise SystemExit(1)
    except Exception as error:
        log(f"AI/API error: {error}", Colors.RED)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
