"""
Meta AI job change detection and ACF JSON preview.

This script only prints JSON. It never calls the WordPress API.
"""

import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from dotenv import load_dotenv
from openai import OpenAI

from compare import get_diff

load_dotenv()
ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "scrape_output"
SITES_FILE = ROOT / "sites.json"
META_API_KEY = os.getenv("META_API_KEY")
META_MODEL = os.getenv("META_MODEL", "muse-spark-1.3-contributor")
UNAVAILABLE = "Unavailable"
BUILD_VERSION = "meta-diff-v5"


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
Compare added and removed HTML evidence. Return only compact valid JSON:
{"changes":[{"action":"create","job_title":"...","job_url":"...","employment_type":"...","job_description":"..."},{"action":"delete","job_title":"...","job_url":"..."}]}

Rules:
- ADDED only = new vacancy (create); REMOVED only = deleted vacancy (delete).
- If the same vacancy appears on both sides, ignore it. Match by URL first, then clear title.
- Analyze every changed line, but ignore non-vacancy changes such as formatting, navigation and tracking.
- Combine split links/titles using surrounding diff lines. Never invent facts.
- For create, include employment_type and job_description only when supported by the diff; otherwise omit them. Resolve relative URLs against SOURCE_URL.
- For delete, return title and URL when available.
- If the supplied HTML is empty or contains no evidence of vacancies, return {"changes":[]}; never guess or invent vacancies.\n- Return {"changes":[]} when no vacancy change is found.
"""


def load_site(site_slug):
    if not SITES_FILE.exists():
        raise FileNotFoundError(f"Missing config: {SITES_FILE}")
    sites = json.loads(SITES_FILE.read_text(encoding="utf-8"))
    for site in sites:
        if site.get("slug") == site_slug:
            return site
    raise ValueError(f"Employer slug not found in sites.json: {site_slug}")


def value_or_unavailable(value):
    return str(value).strip() if value is not None and str(value).strip() else UNAVAILABLE


def diff_section(title, rows, marker):
    if not rows:
        return title + "\n(none)"
    return "\n".join([title] + [f"{marker} [line {number}] {line}" for number, line in rows])


def prepare_input(site, new_file, old_file, first_scan=False, diff=None):
    if not new_file.exists():
        raise FileNotFoundError(f"New HTML file not found: {new_file}")

    metadata = {
        "employer_name": value_or_unavailable(site.get("name")),
        "job_location": value_or_unavailable(site.get("address")),
        "source_url": value_or_unavailable(site.get("url")),
        "canton": value_or_unavailable(site.get("canton")),
        "scope": value_or_unavailable(site.get("scope")),
        "employer_slug": value_or_unavailable(site.get("slug")),
        "scraped_at": date.today().isoformat(),
    }

    new_html = new_file.read_text(encoding="utf-8")

    if first_scan:
        if not new_html.strip():
            html_section = (
                f"=== CURRENT NEW HTML ({new_file.name}) ===\n"
                "[EMPTY HTML: no page content was returned. Do not infer or invent jobs. "
                "Return exactly {\"changes\":[]}.]"
            )
        else:
            html_section = f"=== CURRENT NEW HTML ({new_file.name}) ===\n{new_html}"

        content = (
            "INPUT MODE: FIRST_SCAN\n"
            "There is no previous HTML snapshot. Identify current job vacancies only "
            "when the supplied HTML contains direct evidence. If it is empty or contains "
            "no vacancy evidence, return {\"changes\":[]}. Never invent vacancies. "
            "Return each confirmed current vacancy as action=create.\n\n"
            f"SOURCE_URL: {metadata['source_url']}\n\n"
            f"{html_section}"
        )
        return content, {"mode": "FIRST_SCAN", "added": None, "removed": None}

    if not old_file.exists():
        raise FileNotFoundError(f"Previous HTML snapshot not found: {old_file}")

    if diff is None:
        diff = get_diff(new_file, old_file)

    added, removed = diff["added"], diff["removed"]
    stats = {
        "mode": "DIFF",
        "added": len(added),
        "removed": len(removed),
        "old_lines": diff["old_lines"],
        "new_lines": diff["new_lines"],
    }

    # The ONLY condition that skips Meta AI is an identical HTML snapshot.
    if len(added) == 0 and len(removed) == 0:
        return None, stats

    content = (
        "INPUT MODE: DIFF\n"
        "Determine added and removed vacancies by comparing the new and old HTML "
        "evidence. Both sections are equally important. If the new HTML is empty, "
        "do not invent current vacancies; use only the removed evidence to identify "
        "vacancies that have disappeared.\n\n"
        f"SOURCE_URL: {metadata['source_url']}\n\n"
        f"{diff_section('=== ADDED: PRESENT IN NEW HTML ===', added, '+')}\n\n"
        f"{diff_section('=== REMOVED: PRESENT IN OLD HTML ===', removed, '-')}"
    )
    return content, stats


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
    if not isinstance(data, dict) or not isinstance(data.get("changes"), list):
        raise ValueError('AI response must contain a "changes" array.')

    source_url = value_or_unavailable(site.get("url"))
    manual_metadata = {
        "employer_name": value_or_unavailable(site.get("name")),
        "job_location": value_or_unavailable(site.get("address")),
        "source_url": source_url,
        "canton": value_or_unavailable(site.get("canton")),
        "scope": value_or_unavailable(site.get("scope")),
        "employer_slug": value_or_unavailable(site.get("slug")),
    }

    changes = []
    for number, item in enumerate(data["changes"], 1):
        if not isinstance(item, dict):
            raise ValueError(f"Change #{number} is not an object.")

        action = str(item.get("action", "")).strip().lower()
        if action not in ("create", "delete"):
            raise ValueError(f'Change #{number} has invalid action: {action!r}')

        job_url = value_or_unavailable(item.get("job_url"))
        if job_url != UNAVAILABLE and source_url != UNAVAILABLE:
            job_url = urljoin(source_url, job_url)

        job = {
            "action": action,
            "job_title": value_or_unavailable(item.get("job_title")),
            "job_url": job_url,
        }

        if action == "create":
            job.update({
                **manual_metadata,
                "employment_type": value_or_unavailable(item.get("employment_type")),
                "job_description": value_or_unavailable(item.get("job_description")),
                "scraped_at": date.today().isoformat(),
            })

        changes.append(job)

    return {"changes": changes}


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
    output_details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(output_details, "reasoning_tokens", None) if output_details else None
    accepted_prediction = (
        getattr(output_details, "accepted_prediction_tokens", None)
        if output_details else None
    )
    rejected_prediction = (
        getattr(output_details, "rejected_prediction_tokens", None)
        if output_details else None
    )
    log("\nTOKEN USAGE", Colors.BOLD + Colors.CYAN)
    log(f"Input tokens:  {input_tokens if input_tokens is not None else UNAVAILABLE}")
    log(f"Output tokens: {output_tokens if output_tokens is not None else UNAVAILABLE}")
    if cached is not None:
        log(f"Cached input:  {cached}")
    if reasoning is not None:
        log(f"Reasoning tokens: {reasoning}")
    if accepted_prediction is not None:
        log(f"Accepted prediction tokens: {accepted_prediction}")
    if rejected_prediction is not None:
        log(f"Rejected prediction tokens: {rejected_prediction}")
    if output_details is None:
        log("Output token details: not provided by API", Colors.YELLOW)
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
        extra_body={"prompt_cache_key": "data-scraping-job-extraction-v2"},
        temperature=0,
        reasoning_effort="minimal",
        max_tokens=2000,
    )


def run_ai_pipeline(site_slug, new_file, old_file, first_scan=False, diff=None):
    site = load_site(site_slug)
    user_content, stats = prepare_input(
        site, new_file, old_file, first_scan=first_scan, diff=diff
    )

    log("=" * 78, Colors.BLUE)
    log("META AI REQUEST — DIFF AND ACF JSON PREVIEW", Colors.BOLD + Colors.BLUE)
    log(f"BUILD VERSION: {BUILD_VERSION}", Colors.BOLD + Colors.GREEN)
    log(f"Employer: {site.get('name')} | Slug: {site_slug}", Colors.CYAN)
    log(f"Model: {META_MODEL} | Mode: {stats['mode']}", Colors.CYAN)

    if stats["mode"] == "DIFF":
        log(f"ADDED: {stats['added']} lines | REMOVED: {stats['removed']} lines")
        if user_content is None:
            log("\nHTML snapshots are identical (empty diff). Meta AI was not called.", Colors.GREEN)
            log("No changed content to analyze.", Colors.YELLOW)
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
    log("\n--- FINAL JSON ---", Colors.BOLD + Colors.GREEN)
    print(json.dumps(final_data, ensure_ascii=False, indent=2))

    creates = sum(1 for change in final_data["changes"] if change["action"] == "create")
    deletes = sum(1 for change in final_data["changes"] if change["action"] == "delete")
    log(f"\nNew vacancies (create): {creates}", Colors.GREEN)
    log(f"Removed vacancies (delete): {deletes}", Colors.RED)
    log("WordPress API: NOT CALLED. Nothing was sent to WordPress.", Colors.YELLOW)


def main():
    import sys

    if len(sys.argv) != 2:
        log("Použitie: python ai_prepare.py <slug>", Colors.YELLOW)
        raise SystemExit(2)

    site_slug = sys.argv[1]
    site = load_site(site_slug)
    new_file = OUTPUT / f"{site_slug}.html"
    old_file = OUTPUT / f"{site_slug}-old.html"
    first_scan = not old_file.exists()

    try:
        run_ai_pipeline(site_slug, new_file, old_file, first_scan=first_scan)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError, RuntimeError) as error:
        log(f"ERROR: {error}", Colors.RED)
        raise SystemExit(1)
    except Exception as error:
        log(f"AI/API error: {error}", Colors.RED)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
