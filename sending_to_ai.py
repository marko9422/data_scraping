"""Send additions and removals together to AI; validate the returned JSON."""
import json
import re
from urllib.parse import urljoin, urlsplit


SYSTEM_PROMPT = """
Analyze changes between two versions of a hotel or restaurant careers page.
Input includes ADDED CONTENT (only in new HTML) and REMOVED CONTENT (only in old HTML).
Some changes are unrelated, such as cookie notices, navigation, footer or marketing text.

Return ONLY JSON:
{
  "new_jobs": [{"title":"","url":"","location":"","canton":"","employment_type":"","description":""}],
  "updated_jobs": [{"title":"","url":"","location":"","canton":"","employment_type":"","description":""}],
  "removed_jobs": [{"title":"","url":""}],
  "irrelevant_changes": []
}

Rules:
- Identify actual, specific vacancies only. Never invent jobs or URLs.
- Added vacancies belong in new_jobs unless evidence clearly shows an update.
- Removed vacancies are removal candidates, not proof of permanent closure.
- A job can be removed while another is added in the same page change. Return both independently.
- Classify a changed title or URL as updated only when evidence clearly establishes identity.
- Prefer real href links and resolve relative URLs against the careers page URL.
- Use configured default address and canton only when listing-specific data is absent.
- Return empty arrays when no vacancy matches a category.
"""


def parse_json(content):
    content = (content or "").strip()
    content = re.sub(r"^\x60{3}(?:json)?\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\s*\x60{3}$", "", content)
    return json.loads(content)


def absolute_job_url(job, base_url):
    url = (job.get("url") or "").strip()
    if not url:
        raise ValueError("AI returned a job without URL: " + str(job.get("title")))
    url = urljoin(base_url, url)
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("AI returned invalid URL: " + url)
    return url


def analyze_changes(client, model, site, diff):
    """One request contains added content, removed content and diff context."""
    prompt = f"""
CAREERS PAGE: {site['url']}
EMPLOYER: {site['name']}
EMPLOYER SLUG: {site.get('slug', '')}
DEFAULT ADDRESS: {site.get('address') or 'Unknown'}
DEFAULT CANTON: {site.get('canton') or 'Unknown'}
FIRST RUN: {diff.get('first_run', False)}

========== ADDED CONTENT ==========
{diff.get('added_content') or '[None]'}

========== REMOVED CONTENT =========
{diff.get('removed_content') or '[None]'}

========== UNIFIED DIFF ===========
{diff.get('diff_text') or '[None]'}

Analyze both directions together. Return JSON only.
"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=5000,
    )

    usage = response.usage
    details = getattr(usage, "prompt_tokens_details", None) if usage else None
    token_usage = {
        "input": (getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)) if usage else None,
        "cached": (getattr(details, "cached_tokens", 0) or 0) if details else 0,
        "output": (getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None)) if usage else None,
    }

    data = parse_json(response.choices[0].message.content)
    if not isinstance(data, dict):
        raise ValueError("AI response must be a JSON object")
    for field in ("new_jobs", "updated_jobs", "removed_jobs", "irrelevant_changes"):
        if not isinstance(data.get(field), list):
            raise ValueError("AI response field must be a list: " + field)

    for field in ("new_jobs", "updated_jobs", "removed_jobs"):
        for job in data[field]:
            if not isinstance(job, dict) or not job.get("title"):
                raise ValueError("Invalid job in AI response: " + field)
            job["url"] = absolute_job_url(job, site["url"])

    data["token_usage"] = token_usage
    return data
