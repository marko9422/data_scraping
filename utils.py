"""Shared URL helpers used by diff and WordPress synchronization."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_url(url):
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid", "ref", "source"}
    ]
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower().removeprefix("www."),
        parts.path.rstrip("/") or "/",
        urlencode(query, doseq=True),
        "",
    ))


def url_is_present(url, html):
    """Check if the job detail URL still occurs in the current HTML."""
    target = normalize_url(url)
    if not target:
        return False
    return target in html.replace("&amp;", "&")
