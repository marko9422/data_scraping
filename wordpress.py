"""WordPress REST API operations for job posts."""
from datetime import date

from utils import normalize_url


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
    """Create or update jobs. Match by source_url and normalized job_url."""
    if not jobs:
        return {"created": 0, "updated": 0, "skipped": 0}

    posts = posts_for_site(get_wp_jobs(session, wp_base), site["url"])
    existing = {
        normalize_url((post.get("acf") or {}).get("job_url", "")): post
        for post in posts if (post.get("acf") or {}).get("job_url")
    }
    created = updated = skipped = 0

    for job in jobs:
        url = (job.get("url") or "").strip()
        key = normalize_url(url)
        if not key:
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

        post = existing.get(key)
        if post:
            request(session, "POST", f"{wp_base}/{post['id']}", json=payload)
            updated += 1
        else:
            created_post = request(session, "POST", wp_base, json=payload)
            created += 1
            if isinstance(created_post, dict) and created_post.get("id"):
                existing[key] = created_post

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
