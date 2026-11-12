"""WordPress REST API operations for job posts."""
from datetime import date
import re

from utils import normalize_url


def normalize_title(title):
    """Normalize punctuation and whitespace for a cautious title fallback."""
    return re.sub(r"[^a-z0-9]+", " ", (title or "").casefold()).strip()


def request(session, method, url, **kwargs):
    response = session.request(method, url, timeout=30, **kwargs)
    if not response.ok:
        raise RuntimeError(f"WordPress API {response.status_code}: {response.text}")
    return response.json()


def get_wp_jobs(session, wp_base):
    """Fetch all posts, including ACF fields, with REST pagination."""
    posts = []
    page = 1
    while True:
        batch = request(
            session, "GET", wp_base,
            params={
                "per_page": 100,
                "page": page,
                "context": "edit",
                "_fields": "id,status,title,acf",
            },
        )
        if not batch:
            break
        posts.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return posts


def posts_for_site(posts, source_url):
    source_key = normalize_url(source_url)
    return [
        post for post in posts
        if normalize_url((post.get("acf") or {}).get("source_url", "")) == source_key
    ]


def sync_jobs(session, wp_base, site, jobs):
    """Upsert by URL; use exact normalized title only if it uniquely identifies a post."""
    if not jobs:
        return {"created": 0, "updated": 0, "skipped": 0}

    posts = posts_for_site(get_wp_jobs(session, wp_base), site["url"])
    existing_by_url = {}
    existing_by_title = {}
    for post in posts:
        acf = post.get("acf") or {}
        url_key = normalize_url(acf.get("job_url", ""))
        title_key = normalize_title(acf.get("job_title") or post.get("title", {}).get("rendered", ""))
        if url_key:
            existing_by_url[url_key] = post
        if title_key:
            existing_by_title.setdefault(title_key, []).append(post)

    created = updated = skipped = 0
    for job in jobs:
        url = (job.get("url") or "").strip()
        url_key = normalize_url(url)
        title_key = normalize_title(job.get("title", ""))
        if not url_key or not title_key:
            skipped += 1
            continue

        payload = {
            "title": job["title"],
            "status": "publish",
            "acf": {
                "job_title": job["title"],
                "employer_name": site["name"],
                "job_location": job.get("location") or site.get("address") or "Neznáme",
                "canton": job.get("canton") or site.get("canton") or "Neznáme",
                "employment_type": job.get("employment_type", ""),
                "job_description": job.get("description", ""),
                "job_url": url,
                "source_url": site["url"],
                "scraped_at": date.today().isoformat(),
            },
        }

        post = existing_by_url.get(url_key)
        if post is None:
            title_matches = existing_by_title.get(title_key, [])
            # A title is only a safe fallback if exactly one existing post matches.
            if len(title_matches) == 1:
                post = title_matches[0]

        if post:
            request(session, "POST", f"{wp_base}/{post['id']}", json=payload)
            updated += 1
            existing_by_url[url_key] = post
        else:
            created_post = request(session, "POST", wp_base, json=payload)
            created += 1
            if isinstance(created_post, dict) and created_post.get("id"):
                existing_by_url[url_key] = created_post
                existing_by_title.setdefault(title_key, []).append(created_post)

    return {"created": created, "updated": updated, "skipped": skipped}


def archive_jobs(session, wp_base, site, job_urls):
    """Set matching published posts to draft; never delete them."""
    if not job_urls:
        return 0
    posts = posts_for_site(get_wp_jobs(session, wp_base), site["url"])
    existing = {
        normalize_url((post.get("acf") or {}).get("job_url", "")): post
        for post in posts if (post.get("acf") or {}).get("job_url")
    }
    archived = 0
    for url in job_urls:
        post = existing.get(normalize_url(url))
        if post and post.get("status") == "publish":
            request(session, "POST", f"{wp_base}/{post['id']}", json={"status": "draft"})
            archived += 1
    return archived
