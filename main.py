"""Run the modular scraper: python main.py."""
import asyncio
import os
import time
from pathlib import Path

import requests
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from dotenv import load_dotenv
from openai import OpenAI

from scraping import fetch_and_clean_page, load_sites
from html_diff import create_html_diff
from sending_to_ai import analyze_changes
from wordpress import sync_jobs, archive_jobs
from state import load_state, save_state, snapshot_path, state_path
from utils import normalize_url, url_is_present

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "scrape_output"
WP_BASE = "https://jobs.novarisdev.com/?rest_route=/wp/v2/job"


def create_clients():
    load_dotenv()
    wp_user = os.getenv("WP_USERNAME")
    wp_password = os.getenv("WP_APPLICATION_PASSWORD")
    api_key = os.getenv("META_API_KEY")
    model = os.getenv("META_MODEL", "muse-spark-1.3-contributor")
    if not wp_user or not wp_password:
        raise RuntimeError("Set WP_USERNAME and WP_APPLICATION_PASSWORD in .env")
    if not api_key:
        raise RuntimeError("Set META_API_KEY in .env")
    ai = OpenAI(base_url="https://api.meta.ai/v1", api_key=api_key)
    wp = requests.Session()
    wp.auth = (wp_user, wp_password)
    wp.headers.update({"Content-Type": "application/json"})
    return ai, model, wp


def print_stage(number, title, explanation):
    print(f"\n\033[96m{'=' * 70}\033[0m")
    print(f"\033[1m\033[96mSTEP {number}: {title}\033[0m")
    print(f"\033[90m{explanation}\033[0m")
    print(f"\033[96m{'=' * 70}\033[0m")


def confirm_old_removals(site, state, current_html, wp_session):
    """Confirm only removal candidates that were already pending before this scan."""
    pending = state.setdefault("pending_removals", {})
    confirmed = []
    for key, record in list(pending.items()):
        url = record["url"]
        if url_is_present(url, current_html, site["url"]):
            print(f"  \033[92mRESTORED\033[0m {url}; cancel removal")
            del pending[key]
            continue
        record["missing_scans"] = int(record.get("missing_scans", 1)) + 1
        print(f"  \033[93mABSENT\033[0m {url}: {record['missing_scans']}/2 successful scans")
        if record["missing_scans"] >= 2:
            confirmed.append(url)
    archived = archive_jobs(wp_session, WP_BASE, site, confirmed)
    for url in confirmed:
        pending.pop(normalize_url(url), None)
    return archived


async def process_site(crawler, site, config, ai, model, wp_session):
    started = time.perf_counter()
    html_file = snapshot_path(OUTPUT_DIR, site)
    json_file = state_path(OUTPUT_DIR, site)

    print(f"\n\033[1m\033[95mWEBSITE: {site['name']} ({site.get('slug', '')})\033[0m")
    print_stage(1, "SCRAPING", "Crawl4AI downloads the page; scraping.py removes technical noise.")
    current_html = await fetch_and_clean_page(crawler, site["url"], config)
    print(f"  Clean HTML size: {len(current_html.encode('utf-8')):,} bytes")

    state = load_state(json_file)
    first_run = not html_file.exists()

    print_stage(2, "HTML DIFF", "Python detects added and removed text; it does not identify job semantics.")
    if first_run:
        diff = {
            "changed": True, "first_run": True,
            "added_content": current_html, "removed_content": "",
            "diff_text": current_html,
            "added_lines": len(current_html.splitlines()), "removed_lines": 0,
        }
        print("  FIRST RUN: complete cleaned page sent to AI once.")
    else:
        old_html = html_file.read_text(encoding="utf-8")
        diff = create_html_diff(old_html, current_html)
        if diff["changed"]:
            print(f"  CHANGED: +{diff['added_lines']} lines / -{diff['removed_lines']} lines")
        else:
            print("  UNCHANGED: skip AI.")

    analysis = {
        "new_jobs": [], "updated_jobs": [], "removed_jobs": [],
        "irrelevant_changes": [],
        "token_usage": {"input": None, "cached": 0, "output": None},
    }
    print_stage(3, "SENDING TO AI", "Added and removed HTML are sent together in one request.")
    if diff["changed"]:
        analysis = analyze_changes(ai, model, site, diff)
        print(
            f"  New: {len(analysis['new_jobs'])} | Updated: {len(analysis['updated_jobs'])} | "
            f"Removal candidates: {len(analysis['removed_jobs'])} | "
            f"Irrelevant: {len(analysis['irrelevant_changes'])}"
        )
        usage = analysis["token_usage"]
        print(f"  Tokens: input={usage['input']} cached={usage['cached']} output={usage['output']}")
    else:
        print("  SKIPPED - no changes.")

    print_stage(4, "WORDPRESS UPSERT", "Match by source_url and normalized job_url.")
    active = [dict(job, _change_type="new") for job in analysis["new_jobs"]] + [dict(job, _change_type="updated") for job in analysis["updated_jobs"]]
    result = sync_jobs(wp_session, WP_BASE, site, active)
    print(f"  Created: {result['created']} | Updated: {result['updated']} | Skipped: {result['skipped']}")

    # Confirm old candidates BEFORE adding new ones; a fresh candidate stays at 1/2.
    print_stage(5, "REMOVAL CHECK", "A removal candidate must remain absent on two successful scans.")
    archived = confirm_old_removals(site, state, current_html, wp_session)
    pending = state.setdefault("pending_removals", {})
    for job in analysis["removed_jobs"]:
        url = job.get("url")
        if not url:
            continue
        key = normalize_url(url)
        if url_is_present(url, current_html, site["url"]):
            print(f"  NOT QUEUED: URL is still present: {url}")
            continue
        if key not in pending:
            pending[key] = {"url": url, "title": job.get("title", ""), "missing_scans": 1}
            print(f"  QUEUED: {job.get('title') or url} (1/2)")
    print(f"  Drafted: {archived} | Pending: {len(pending)}")

    print_stage(6, "SAVE SNAPSHOT", "Failed runs do not advance the baseline; next run can retry.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_file.write_text(current_html, encoding="utf-8")
    state["last_successful_scan"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(json_file, state)
    print(f"  Saved {html_file.name} and {json_file.name}")
    print(f"\033[92mDONE in {time.perf_counter() - started:.1f}s\033[0m")


async def main():
    load_dotenv()
    ai, model, wp_session = create_clients()
    sites = load_sites(ROOT / "sites.json")
    browser = BrowserConfig(headless=True)
    config = CrawlerRunConfig(wait_until="networkidle", page_timeout=60000)
    async with AsyncWebCrawler(config=browser) as crawler:
        for site in sites:
            try:
                await process_site(crawler, site, config, ai, model, wp_session)
            except Exception as exc:
                print(f"\n\033[91mERROR for {site['name']}: {exc}\033[0m")
                print("Snapshot was not advanced; the next run can retry.")


if __name__ == "__main__":
    asyncio.run(main())
