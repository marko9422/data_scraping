import asyncio
import json
import os
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
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


# Keep these instructions identical between requests so the provider can
# reuse the same prompt prefix through automatic prompt caching.
SYSTEM_PROMPT = """
Extract current, specific job vacancies from the supplied cleaned HTML.
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
- Determine each job's workplace from the job listing first. If absent, look for the employer/hotel address elsewhere in the supplied HTML (contact, footer, address, location sections).
- For Swiss locations, append the canton when it is explicitly stated or can be identified confidently from the stated address/locality. Format, for example, "Stoos, Kanton Schwyz" or "Zürich, Kanton Zürich".
- If the workplace/address or canton cannot be determined reliably, use exactly "Neznáme". Never guess.
- Resolve relative links using the website URL supplied in the user message.
- If there are no vacancies, return an empty jobs array.
"""


def extract_jobs(html, source_url, employer_hint):
    """Send stable instructions plus website-specific HTML and return token usage."""
    response = ai.chat.completions.create(
        model=META_MODEL,
        messages=[
            # Stable system prompt comes first and is the cacheable prefix.
            {"role": "system", "content": SYSTEM_PROMPT},
            # Website-specific content changes, so it follows the stable prompt.
            {
                "role": "user",
                "content": (
                    f"Website URL: {source_url}\n"
                    f"Employer hint: {employer_hint}\n\n"
                    f"HTML:\n{html}"
                ),
            },
        ],
        temperature=0,
        max_tokens=4000,
    )

    # Providers may report cached tokens inside prompt_tokens_details.
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

    # Validate the AI response before allowing it to reach WordPress.
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("AI response does not match expected JSON schema")

    for job in data["jobs"]:
        if not job.get("title") or not job.get("url"):
            raise ValueError("AI returned a job without title or URL")
        # Convert relative job links into absolute URLs.
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


def sync_jobs(site, extracted):
    """Create new jobs, update matching jobs and draft jobs no longer found."""
    source_url = site["url"]
    employer = extracted.get("employer") or site["name"]
    existing = get_wp_jobs()

    # Match posts by job URL, but only within the current source website.
    matching = {
        post.get("acf", {}).get("job_url"): post
        for post in existing
        if post.get("acf", {}).get("source_url") == source_url
        and post.get("acf", {}).get("job_url")
    }

    seen = set()
    created = updated = archived = 0
    today = date.today().isoformat()

    for job in extracted["jobs"]:
        url = job["url"]
        seen.add(url)

        # Map the extracted vacancy to the WordPress title and ACF fields.
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
            # Existing URL: update the WordPress post instead of creating a duplicate.
            wp_request("POST", f"{WP_BASE}/{matching[url]['id']}", json=payload)
            updated += 1
        else:
            # New URL: create a new published job post.
            wp_request("POST", json=payload)
            created += 1

    # Draft old listings missing from a non-empty AI result.
    # An empty AI result is treated cautiously and never archives everything.
    if extracted["jobs"]:
        for url, post in matching.items():
            if url not in seen and post.get("status") == "publish":
                wp_request("POST", f"{WP_BASE}/{post['id']}", json={"status": "draft"})
                archived += 1

    print(f"  WordPress: +{created} new | {updated} updated | {archived} drafted")
    return {"created": created, "updated": updated, "archived": archived}


def print_summary(results):
    """Print a compact per-website report and totals for the whole run."""
    columns = ("Website", "HTML", "AI", "Jobs", "Input tok.", "Cached tok.", "Output tok.", "Cache %", "Time")
    rows = []

    for item in results:
        rows.append((
            item["site"],
            item["html"],
            item["ai"],
            str(item["jobs"]),
            str(item["input_tokens"]) if item["input_tokens"] is not None else "N/A",
            str(item["cached_tokens"]) if item["cached_tokens"] is not None else "N/A",
            str(item["output_tokens"]) if item["output_tokens"] is not None else "N/A",
            (
                f'{item["cached_tokens"] / item["input_tokens"] * 100:.1f}%'
                if item["input_tokens"] else "N/A"
            ),
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
    cache_rate = total_cached / total_input * 100 if total_input else 0
    total_jobs = sum(x["jobs"] for x in results)
    total_created = sum(x["created"] for x in results)
    total_updated = sum(x["updated"] for x in results)
    total_archived = sum(x["archived"] for x in results)

    print("-" * (sum(widths) + 3 * len(widths) + 1))
    print(
        f"TOTAL | Jobs found: {total_jobs} | Input tokens: {total_input} "
        f"| Cached tokens: {total_cached} | Cache hit rate: {cache_rate:.1f}% "
        f"| Output tokens: {total_output}"
    )
    print(
        f"WordPress total: {total_created} created, {total_updated} updated, "
        f"{total_archived} drafted"
    )
    print("N/A means the AI provider did not return token usage for that request.")
    print("=" * (sum(widths) + 3 * len(widths) + 1))


async def process_site(crawler, site, config):
    """Scrape one website, detect HTML changes and run AI/WordPress only if needed."""
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

    # Download the page with Crawl4AI.
    result = await crawler.arun(url=site["url"], config=config)
    if not result.success:
        raise RuntimeError(result.error_message or "Crawl failed")

    raw_html = result.html or result.cleaned_html
    if not raw_html:
        raise RuntimeError("Page returned empty HTML")

    # Remove unnecessary HTML and prepare a local file for change detection.
    cleaned = clean_html(raw_html)
    path = OUTPUT_DIR / make_filename(site)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # First run is considered changed because no previous snapshot exists.
    first_run = not path.exists()
    changed = True
    if not first_run:
        old = path.read_text(encoding="utf-8")
        changed = (
            normalize_html_for_comparison(old)
            != normalize_html_for_comparison(cleaned)
        )

    stats["html"] = "FIRST RUN" if first_run else ("CHANGED" if changed else "SAME")
    print(f"  HTML: {stats['html']}")

    if not changed:
        # No HTML change: save AI tokens and WordPress API calls.
        print("  No meaningful HTML change; skipping AI and WordPress sync.")
        stats["seconds"] = time.perf_counter() - started
        return stats

    # Ask AI to identify vacancies only when the page has changed.
    stats["ai"] = "YES"
    extracted, token_usage = extract_jobs(cleaned, site["url"], site["name"])
    stats["input_tokens"] = token_usage["input"]
    stats["cached_tokens"] = token_usage["cached"]
    stats["output_tokens"] = token_usage["output"]
    stats["jobs"] = len(extracted["jobs"])

    print(
        f"  AI: {stats['jobs']} jobs | "
        f"tokens in={stats['input_tokens']} cached={stats['cached_tokens']} "
        f"out={stats['output_tokens']}"
    )

    if not extracted["jobs"]:
        print("  AI found no jobs; existing WordPress listings remain unchanged.")
    else:
        wp_stats = sync_jobs(site, extracted)
        stats.update(wp_stats)

    # Store the new snapshot after successful extraction/synchronization.
    path.write_text(cleaned, encoding="utf-8")
    print(f"  Saved HTML snapshot: {path.name}")

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
