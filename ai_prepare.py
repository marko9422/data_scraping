"""
Meta AI job change detection and ACF JSON preview.

This script only prints JSON. It never calls the WordPress API.
"""

import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

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
BUILD_VERSION = "meta-diff-v7"

# Fixed English category IDs. AI must choose exactly one for each CREATE.
CATEGORIES = {
    "kitchen": "Kitchen roles: chef, cook, kitchen assistant, dishwasher, pizzaiolo.",
    "service": "Restaurant service roles: waiter, waitress, service staff, chef de rang.",
    "reception": "Reception and front-office roles: receptionist, front desk, guest relations.",
    "housekeeping": "Housekeeping and cleaning roles: room attendant, cleaner, housekeeping staff.",
    "management": "Management roles: restaurant manager, hotel manager, head chef, department manager.",
    "office": "Office and administration roles: HR, accounting, marketing, administration.",
    "bar": "Bar roles: bartender, barista, bar staff.",
    "wellness": "Wellness and spa roles: masseur, spa therapist, spa staff.",
    "technical": "Technical and facility roles: technician, maintenance, caretaker, facility staff.",
    "apprenticeship": "Apprenticeships, traineeships and internships: apprentice, learner, intern.",
    "other": "Use only when the position does not clearly fit another category.",
}

CATEGORY_INSTRUCTIONS = "\n".join(
    f"- {category}: {description}" for category, description in CATEGORIES.items()
)


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


SYSTEM_PROMPT = f"""
Compare added and removed HTML evidence. Return only compact valid JSON:
{{"changes":[{{"action":"create","job_title":"...","job_url":"...","job_category":"kitchen","employment_type":"...","job_description":"..."}},{{"action":"delete","job_title":"...","job_url":"..."}}]}}

Allowed job_category values for CREATE (choose exactly one):
{CATEGORY_INSTRUCTIONS}

Rules:
- ADDED only = new vacancy (create); REMOVED only = deleted vacancy (delete).
- If the same vacancy appears on both sides, ignore it. Match by URL first, then clear title.
- Analyze every changed line, but ignore non-vacancy changes such as formatting, navigation and tracking.
- Combine split links/titles using surrounding diff lines. Never invent facts.
- For create, assign exactly one allowed job_category based primarily on the job title. Return the English category ID exactly as listed. Never invent category values. Use "other" only if no category fits.
- For create, include employment_type and job_description only when supported by the diff; otherwise omit them. Resolve relative URLs against SOURCE_URL.
- For delete, return title and URL when available. Do not include job_category for delete.
- Do not generate job_id. Python generates job_id from employer_slug and normalized job_url.
- If the supplied HTML is empty or contains no evidence of vacancies, return {{"changes":[]}}; never guess or invent vacancies.
- Return {{"changes":[]}} when no vacancy change is found.
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


def normalize_job_url(job_url, source_url=None):
    """Resolve and normalize a job URL so the same vacancy gets the same ID."""
    absolute_url = urljoin(source_url or "", str(job_url).strip())
    parsed = urlsplit(absolute_url)

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if scheme not in ("http", "https") or not hostname:
        raise ValueError(f"Invalid job URL: {job_url!r}")

    port = parsed.port
    netloc = hostname
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    # Remove tracking parameters, but keep other query parameters that may identify a vacancy.
    tracking_names = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"}
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in tracking_names
    ]
    query_items.sort()

    return urlunsplit((scheme, netloc, path, urlencode(query_items, doseq=True), ""))


def generate_job_id(employer_slug, job_url):
    """Stable SHA-256 ID from employer_slug + normalized job_url."""
    slug = str(employer_slug or "").strip().lower()
    if not slug:
        raise ValueError("Cannot generate job_id: employer_slug is missing.")
    identity = f"{slug}|{job_url}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def build_acf_json(data, site):
    if not isinstance(data, dict) or not isinstance(data.get("changes"), list):
        raise ValueError('AI response must contain a "changes" array.')

    source_url = value_or_unavailable(site.get("url"))
    employer_slug = value_or_unavailable(site.get("slug"))
    if employer_slug == UNAVAILABLE:
        raise ValueError("Cannot generate job_id: employer slug is missing.")

    manual_metadata = {
        "employer_name": value_or_unavailable(site.get("name")),
        "job_location": value_or_unavailable(site.get("address")),
        "source_url": source_url,
        "canton": value_or_unavailable(site.get("canton")),
        "scope": value_or_unavailable(site.get("scope")),
        "employer_slug": employer_slug,
    }

    changes = []
    for number, item in enumerate(data["changes"], 1):
        if not isinstance(item, dict):
            raise ValueError(f"Change #{number} is not an object.")

        action = str(item.get("action", "")).strip().lower()
        if action not in ("create", "delete"):
            raise ValueError(f'Change #{number} has invalid action: {action!r}')

        raw_job_url = value_or_unavailable(item.get("job_url"))
        if raw_job_url == UNAVAILABLE:
            raise ValueError(
                f"Change #{number} is missing job_url; cannot safely generate job_id."
            )

        job_url = normalize_job_url(
            raw_job_url,
            source_url if source_url != UNAVAILABLE else None,
        )
        job_id = generate_job_id(employer_slug, job_url)

        job = {
            "action": action,
            "job_id": job_id,
            "job_title": value_or_unavailable(item.get("job_title")),
            "job_url": job_url,
        }

        if action == "create":
            job_category = str(item.get("job_category", "")).strip().lower()
            if job_category not in CATEGORIES:
                raise ValueError(
                    f"Change #{number} has invalid job_category {job_category!r}. "
                    f"Allowed values: {', '.join(CATEGORIES)}"
                )

            job.update({
                **manual_metadata,
                "job_category": job_category,
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

    # Prázdny prvý snapshot nemá dôkaz o pracovných ponukách.
    # V tomto prípade je bezpečnejšie AI vôbec nevolať.
    if first_scan and not new_file.read_text(encoding="utf-8").strip():
        final_data = {"changes": []}
        log("\\nPrvý HTML snapshot je prázdny. Meta AI sa nevolá, aby nevymyslela pracovné ponuky.", Colors.YELLOW)
        log("\\n--- FINAL JSON ---", Colors.BOLD + Colors.GREEN)
        print(json.dumps(final_data, ensure_ascii=False, indent=2))
        log("WordPress API: NOT CALLED.", Colors.YELLOW)
        return

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
