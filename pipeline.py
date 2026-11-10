import asyncio
import hashlib
import json
import os
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from dotenv import load_dotenv
from openai import OpenAI

from scrape import clean_html, normalize_html_for_comparison, load_sites, make_filename

# Load credentials and configuration from the local .env file.
load_dotenv()

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "scrape_output"
WP_BASE = "https://jobs.novarisdev.com/?rest_route=/wp/v2/job"

WP_USER = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APPLICATION_PASSWORD")
META_API_KEY = os.getenv("META_API_KEY")
META_MODEL = os.getenv("META_MODEL", "muse-spark-1.3-contributor")

# Stop immediately if required credentials are missing.
if not WP_USER or not WP_APP_PASSWORD:
    raise RuntimeError("Set WP_USERNAME and WP_APPLICATION_PASSWORD in .env")
if not META_API_KEY:
    raise RuntimeError("Set META_API_KEY in .env")

# Configure the Meta-compatible AI client and authenticated WordPress session.
ai = OpenAI(base_url="https://api.meta.ai/v1", api_key=META_API_KEY)
session = requests.Session()
session.auth = (WP_USER, WP_APP_PASSWORD)
session.headers.update({"Content-Type": "application/json"})


# Stable instructions are kept first so automatic prompt caching can reuse them.
SYSTEM_PROMPT = """
Extract current, specific job vacancies from the supplied website listing snippets.
Return ONLY valid JSON with this schema:
{
  "employer": "employer name or Unknown",
  "jobs": [
    {
      "title": "job title",
      "url": "absolute job URL",
      "location": "workplace address or locality, followed by the Swiss canton when reliably known; otherwise exactly \\"Neznáme\\"",
      "employment_type": "",
      "description": ""
    }
  ]
}
Rules:
- Only actual vacancies, not navigation or general pages. Do not invent facts.
- Use the listing content supplied for each job. If workplace or canton is not reliably present, use exactly "Neznáme".
- For Swiss locations, append the canton when it is explicitly stated or can be identified confidently. Examples: "Stoos, Kanton Schwyz" or "Zürich, Kanton Zürich".
- Resolve relative links against the website URL supplied in the user message.
- If no actual vacancies are present, return an empty jobs array.
"""


def extract_job_candidates(raw_html, source_url):
    """Find compact text blocks around links; each link is a candidate job identity."""
    soup = BeautifulSoup(raw_html, "html.parser")

    # Remove non-content elements before finding listing blocks.
    for tag in soup.find_all([
        "script", "style", "noscript", "svg", "canvas", "img", "picture",
        "video", "audio", "iframe", "object", "embed"
    ]):
        tag.decompose()

    candidates = {}

    for link in soup.find_all("a", href=True):
        href = urljoin(source_url, link["href"].strip())
        if not href.startswith(("http://", "https://")):
            continue

        label = link.get_text(" ", strip=True)
        if not label:
            continue

        # Walk up from the link and select the nearest reasonably sized listing block.
        block = link
        selected_text = ""
        for _ in range(6):
            text = " ".join(block.get_text(" ", strip=True).split())
            link_count = len(block.find_all("a", href=True))
            if 60 <= len(text) <= 3000 and link_count <= 5:
                selected_text = text
                break
            if block.parent is None:
                break
            block = block.parent

        if not selected_text:
            continue

        # Include the target URL in the hash so a changed link is detected too.
        content = f"URL: {href}\n{selected_text}"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # The same job link may appear more than once (e.g. title and apply button).
        previous = candidates.get(href)
        if previous is None or len(content) > len(previous["content"]):
            candidates[href] = {
                "url": href,
                "content": content,
                "content_hash": content_hash,
            }

    return list(candidates.values())


def load_job_state(path):
    """Load the previous per-website job and candidate snapshot."""
    if not path.exists():
        return {"candidates": {}, "jobs": {}}

    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("Invalid state format")
        state.setdefault("candidates", {})
        state.setdefault("jobs", {})
        return state
    except (json.JSONDecodeError, ValueError):
        # Do not overwrite an unreadable state file silently.
        raise RuntimeError(f"Could not read job state file: {path}")


def save_job_state(path, state):
    """Persist the latest candidate hashes and extracted job records."""
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_jobs(html, source_url, employer_hint):
    """Send only new/changed listing snippets to AI and return extracted jobs and usage."""
    response = ai.chat.completions.create(
        model=META_MODEL,
        messages=[
            # This stable prefix is identical for every website and request.
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Website URL: {source_url}\n"
                    f"Employer hint: {employer_hint}\n\n"
                    f"Changed listing snippets:\n{html}"
                ),
            },
        ],
        temperature=0,
        max_tokens=4000,
    )

    # Read regular and cached input token usage when the provider returns it.
    usage = response.usage
    prompt_details = getattr(usage, "prompt_tokens_details", None) if usage else None
    cached_tokens = (
        getattr(prompt_details, "cached_tokens", 0)
        if prompt_details is not None else 0
    ) or 0

    token_usage = {
        "input": (
            getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
        ) if usage else None,
        "cached": cached_tokens,
        "output": (
            getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None)
        ) if usage else None,
    }

    raw = response.choices[0].message.content or ""
    data = json.loads(raw)

    # Validate the AI response before it can affect WordPress.
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("AI response does not match expected JSON schema")

    for job in data["jobs"]:
        if not job.get("title") or not job.get("url"):
            raise ValueError("AI returned a job without title or URL")
        job["url"] = urljoin(source_url, job["url"])

    return data, token_usage

def wp_request(method, url=WP_BASE, **kwargs):
    """Send one authenticated request to the WordPress REST API."""
    response = session.request(method, url, timeout=30, **kwargs)
    if not response.ok:
        raise RuntimeError(f"WordPress API {response.status_code}: {response.text}")
    return response.json()


def get_wp_jobs():
    """Fetch all job posts from WordPress, including editable ACF fields."""
    posts = []
    page = 1

    # WordPress REST API returns a maximum of 100 posts per page here.
    while True:
        batch = wp_request("GET", WP_BASE, params={
            "per_page": 100,
            "page": page,
            "context": "edit",
            "_fields": "id,status,title,acf",
        })
        if not batch:
            break
        posts.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    return posts


def sync_jobs(site, extracted, archive_urls=None):
    """Create/update supplied jobs and archive only explicitly confirmed removals."""
    source_url = site["url"]
    employer = extracted.get("employer") or site["name"]
    existing = get_wp_jobs()

    # Match posts by job URL, scoped to the current source website.
    matching = {
        post.get("acf", {}).get("job_url"): post
        for post in existing
        if post.get("acf", {}).get("source_url") == source_url
        and post.get("acf", {}).get("job_url")
    }

    created = updated = archived = 0
    today = date.today().isoformat()

    for job in extracted.get("jobs", []):
        url = job["url"]
        payload = {
            "title": job["title"],
            "status": "publish",
            "acf": {
                "job_title": job["title"],
                "employer_name": employer,
                "job_location": job.get("location", ""),
                "employment_type": job.get("employment_type", ""),
                "job_description": job.get("description", ""),
                "job_url": url,
                "source_url": source_url,
                "scraped_at": today,
            },
        }

        if url in matching:
            wp_request("POST", f"{WP_BASE}/{matching[url]['id']}", json=payload)
            updated += 1
        else:
            wp_request("POST", json=payload)
            created += 1

    # The caller passes only URLs missing from two successful consecutive scans.
    for url in archive_urls or []:
        post = matching.get(url)
        if post and post.get("status") == "publish":
            wp_request("POST", f"{WP_BASE}/{post['id']}", json={"status": "draft"})
            archived += 1

    print(f"  WordPress: +{created} new | {updated} updated | {archived} drafted")
    return {"created": created, "updated": updated, "archived": archived}

def print_summary(results):
    """Print per-website extraction, token, WordPress and timing statistics."""
    columns = (
        "Website", "HTML", "AI", "Jobs", "Input", "Cached",
        "Output", "Cache %", "New", "Updated", "Drafted", "Time"
    )
    rows = []

    for item in results:
        input_tokens = item["input_tokens"]
        cached_tokens = item["cached_tokens"]
        rows.append((
            item["site"],
            item["html"],
            item["ai"],
            str(item["jobs"]),
            str(input_tokens) if input_tokens is not None else "N/A",
            str(cached_tokens) if cached_tokens is not None else "N/A",
            str(item["output_tokens"]) if item["output_tokens"] is not None else "N/A",
            f'{cached_tokens / input_tokens * 100:.1f}%'
            if input_tokens and cached_tokens is not None else "N/A",
            str(item["created"]),
            str(item["updated"]),
            str(item["archived"]),
            f'{item["seconds"]:.1f}s',
        ))

    widths = [
        max(len(columns[i]), *(len(row[i]) for row in rows))
        for i in range(len(columns))
    ]

    print("\n" + "=" * (sum(widths) + 3 * len(widths) + 1))
    print("PIPELINE SUMMARY")
    print("-" * (sum(widths) + 3 * len(widths) + 1))
    print(" | ".join(columns[i].ljust(widths[i]) for i in range(len(columns))))
    print("-" * (sum(widths) + 3 * len(widths) + 1))

    for row in rows:
        print(" | ".join(row[i].ljust(widths[i]) for i in range(len(columns))))

    total_input = sum(x["input_tokens"] or 0 for x in results)
    total_cached = sum(x["cached_tokens"] or 0 for x in results)
    total_output = sum(x["output_tokens"] or 0 for x in results)
    total_jobs = sum(x["jobs"] for x in results)
    total_created = sum(x["created"] for x in results)
    total_updated = sum(x["updated"] for x in results)
    total_archived = sum(x["archived"] for x in results)
    cache_rate = total_cached / total_input * 100 if total_input else 0

    print("-" * (sum(widths) + 3 * len(widths) + 1))
    print(
        f"TOTAL | Jobs processed: {total_jobs} | Input: {total_input} "
        f"| Cached: {total_cached} ({cache_rate:.1f}%) | Output: {total_output}"
    )
    print(
        f"WordPress: {total_created} created, {total_updated} updated, "
        f"{total_archived} drafted"
    )
    print("=" * (sum(widths) + 3 * len(widths) + 1))

async def process_site(crawler, site, config):
    """Scrape one site and send only new/changed listing blocks to AI."""
    started = time.perf_counter()
    stats = {
        "site": site["name"],
        "html": "ERROR",
        "ai": "NO",
        "jobs": 0,
        "input_tokens": None,
        "cached_tokens": None,
        "output_tokens": None,
        "created": 0,
        "updated": 0,
        "archived": 0,
        "seconds": 0,
    }

    print(f"\nScraping {site['name']}: {site['url']}")
    result = await crawler.arun(url=site["url"], config=config)
    if not result.success:
        raise RuntimeError(result.error_message or "Crawl failed")

    raw_html = result.html or result.cleaned_html
    if not raw_html:
        raise RuntimeError("Page returned empty HTML")

    cleaned = clean_html(raw_html)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Keep the cleaned page snapshot for diagnostics and whole-page fallback.
    html_path = OUTPUT_DIR / make_filename(site)
    first_html_run = not html_path.exists()
    html_changed = True
    if not first_html_run:
        old_html = html_path.read_text(encoding="utf-8")
        html_changed = (
            normalize_html_for_comparison(old_html)
            != normalize_html_for_comparison(cleaned)
        )
    stats["html"] = "FIRST RUN" if first_html_run else ("CHANGED" if html_changed else "SAME")
    print(f"  HTML: {stats['html']}")

    # Keep a separate state file with hashes and previously extracted job data.
    state_path = OUTPUT_DIR / f"{Path(make_filename(site)).stem}_jobs.json"
    state = load_job_state(state_path)
    old_candidates = state["candidates"]
    old_jobs = state["jobs"]

    # Extract compact listing snippets from the original HTML (before layout tags
    # are unwrapped by clean_html), then compare each URL and its content hash.
    candidates = extract_job_candidates(raw_html, site["url"])
    current_candidates = {item["url"]: item for item in candidates}
    current_urls = set(current_candidates)

    new_or_changed = [
        item for item in candidates
        if old_candidates.get(item["url"]) != item["content_hash"]
    ]

    extracted = {"employer": site["name"], "jobs": []}
    token_usage = {"input": None, "cached": None, "output": None}
    archive_urls = []

    if candidates:
        # Only changed listing snippets are sent to AI; unchanged jobs stay local.
        if new_or_changed:
            stats["ai"] = "YES"
            snippets = "\n\n--- LISTING ---\n\n".join(
                item["content"] for item in new_or_changed
            )
            extracted, token_usage = extract_jobs(
                snippets, site["url"], site["name"]
            )
            stats["jobs"] = len(extracted["jobs"])
            stats["input_tokens"] = token_usage["input"]
            stats["cached_tokens"] = token_usage["cached"]
            stats["output_tokens"] = token_usage["output"]

            # Save newly extracted or changed jobs in the local state.
            for job in extracted["jobs"]:
                url = job["url"]
                candidate = current_candidates.get(url)
                old_jobs[url] = {
                    **job,
                    "content_hash": (
                        candidate["content_hash"] if candidate
                        else hashlib.sha256(
                            json.dumps(job, sort_keys=True).encode("utf-8")
                        ).hexdigest()
                    ),
                    "missing_scans": 0,
                    "archived": False,
                }

        # Count consecutive successful scans where a previously known job link
        # is absent. A job is drafted only after it is missing twice.
        for url, record in list(old_jobs.items()):
            if url in current_urls:
                record["missing_scans"] = 0
                continue

            record["missing_scans"] = record.get("missing_scans", 0) + 1
            if record["missing_scans"] >= 2 and not record.get("archived", False):
                archive_urls.append(url)
                record["archived"] = True

        # Update candidate hashes only after AI processing completed successfully.
        state["candidates"] = {
            item["url"]: item["content_hash"] for item in candidates
        }

    else:
        # Fallback for sites whose HTML structure does not expose usable listing
        # cards. Use the existing whole-page extraction only when page HTML changed.
        if html_changed:
            print("  No listing blocks detected; using whole-page AI fallback.")
            stats["ai"] = "YES (fallback)"
            extracted, token_usage = extract_jobs(cleaned, site["url"], site["name"])
            stats["jobs"] = len(extracted["jobs"])
            stats["input_tokens"] = token_usage["input"]
            stats["cached_tokens"] = token_usage["cached"]
            stats["output_tokens"] = token_usage["output"]
            if extracted["jobs"]:
                sync_stats = sync_jobs(site, extracted)
                stats.update(sync_stats)
        else:
            print("  No listing blocks detected; HTML unchanged, skipping AI.")

    # Sync only the changed/new AI results and jobs confirmed missing twice.
    if candidates and (extracted["jobs"] or archive_urls):
        sync_stats = sync_jobs(site, extracted, archive_urls=archive_urls)
        stats.update(sync_stats)

    # Persist state and HTML only after the processing/sync path succeeded.
    save_job_state(state_path, state)
    html_path.write_text(cleaned, encoding="utf-8")
    print(
        f"  Listings: {len(candidates)} candidates | "
        f"{len(new_or_changed) if candidates else 0} new/changed | "
        f"{len(archive_urls)} confirmed removals"
    )
    if stats["ai"] != "NO":
        print(
            f"  AI tokens: input={stats['input_tokens']} "
            f"cached={stats['cached_tokens']} output={stats['output_tokens']}"
        )
    else:
        print("  No AI request needed; all listing blocks are unchanged.")

    stats["seconds"] = time.perf_counter() - started
    return stats

async def main():
    """Run the scraper for every configured website and print a final report."""
    sites = load_sites()
    results = []

    browser = BrowserConfig(headless=True)
    config = CrawlerRunConfig(wait_until="networkidle", page_timeout=60000)

    async with AsyncWebCrawler(config=browser) as crawler:
        for site in sites:
            try:
                stats = await process_site(crawler, site, config)
            except Exception as exc:
                # Keep processing the remaining websites if one website fails.
                print(f"  ERROR for {site['name']}: {exc}")
                stats = {
                    "site": site["name"],
                    "html": "ERROR",
                    "ai": "UNKNOWN",
                    "jobs": 0,
                    "input_tokens": None,
                    "cached_tokens": None,
                    "output_tokens": None,
                    "created": 0,
                    "updated": 0,
                    "archived": 0,
                    "seconds": 0,
                }
            results.append(stats)

    print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
