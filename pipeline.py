import asyncio
import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from dotenv import load_dotenv
from openai import OpenAI

from scrape import clean_html, normalize_html_for_comparison, load_sites, make_filename

load_dotenv()

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "scrape_output"
WP_BASE = "https://jobs.novarisdev.com/?rest_route=/wp/v2/job"
WP_USER = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APPLICATION_PASSWORD")
META_API_KEY = os.getenv("META_API_KEY")
META_MODEL = os.getenv("META_MODEL", "muse-spark-1.3-contributor")

if not WP_USER or not WP_APP_PASSWORD:
    raise RuntimeError("Set WP_USERNAME and WP_APPLICATION_PASSWORD in .env")
if not META_API_KEY:
    raise RuntimeError("Set META_API_KEY in .env")

ai = OpenAI(base_url="https://api.meta.ai/v1", api_key=META_API_KEY)
session = requests.Session()
session.auth = (WP_USER, WP_APP_PASSWORD)
session.headers.update({"Content-Type": "application/json"})


def extract_jobs(html, source_url, employer_hint):
    prompt = f"""
Extract current, specific job vacancies from this cleaned HTML.
Return ONLY valid JSON with this schema:
{{
  "employer": "employer name or Unknown",
  "jobs": [
    {{
      "title": "job title",
      "url": "absolute job URL",
      "location": "",
      "employment_type": "",
      "description": ""
    }}
  ]
}}
Rules: Only actual vacancies, not navigation or general pages. Do not invent facts.
Resolve relative links against {source_url}. Employer hint: {employer_hint}.
If there are no vacancies, return an empty jobs array.
HTML:
{html}
"""
    response = ai.chat.completions.create(
        model=META_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=4000,
    )
    raw = response.choices[0].message.content or ""
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("AI response does not match expected JSON schema")
    for job in data["jobs"]:
        if not job.get("title") or not job.get("url"):
            raise ValueError("AI returned a job without title or URL")
        job["url"] = urljoin(source_url, job["url"])
    return data


def wp_request(method, url=WP_BASE, **kwargs):
    response = session.request(method, url, timeout=30, **kwargs)
    if not response.ok:
        raise RuntimeError(f"WordPress API {response.status_code}: {response.text}")
    return response.json()


def get_wp_jobs():
    posts = []
    page = 1
    while True:
        batch = wp_request("GET", WP_BASE, params={
            "per_page": 100, "page": page, "context": "edit", "_fields": "id,status,title,acf"
        })
        if not batch:
            break
        posts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return posts


def sync_jobs(site, extracted):
    source_url = site["url"]
    employer = extracted.get("employer") or site["name"]
    existing = get_wp_jobs()
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

    # Only archive missing listings after AI returned at least one valid listing.
    # This avoids mass-archiving if the source temporarily yields an empty result.
    if extracted["jobs"]:
        for url, post in matching.items():
            if url not in seen and post.get("status") == "publish":
                wp_request("POST", f"{WP_BASE}/{post['id']}", json={"status": "draft"})
                archived += 1

    print(f"WordPress sync: created={created}, updated={updated}, archived={archived}")


async def process_site(crawler, site, config):
    print(f"\nScraping {site['name']}: {site['url']}")
    result = await crawler.arun(url=site["url"], config=config)
    if not result.success:
        raise RuntimeError(result.error_message or "Crawl failed")
    raw_html = result.html or result.cleaned_html
    if not raw_html:
        raise RuntimeError("Page returned empty HTML")

    cleaned = clean_html(raw_html)
    path = OUTPUT_DIR / make_filename(site)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    changed = True
    if path.exists():
        old = path.read_text(encoding="utf-8")
        changed = normalize_html_for_comparison(old) != normalize_html_for_comparison(cleaned)
    if not changed:
        print("No meaningful HTML change; skipping AI and WordPress sync.")
        return

    extracted = extract_jobs(cleaned, site["url"], site["name"])
    if not extracted["jobs"]:
        print("AI found no jobs; leaving existing WordPress listings unchanged.")
    else:
        sync_jobs(site, extracted)

    path.write_text(cleaned, encoding="utf-8")
    print(f"Saved updated HTML: {path.name}")


async def main():
    sites = load_sites()
    browser = BrowserConfig(headless=True)
    config = CrawlerRunConfig(wait_until="networkidle", page_timeout=60000)
    async with AsyncWebCrawler(config=browser) as crawler:
        for site in sites:
            try:
                await process_site(crawler, site, config)
            except Exception as exc:
                print(f"ERROR for {site['name']}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
