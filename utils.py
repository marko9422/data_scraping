"""Shared URL normalization and page-presence helpers."""
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

from bs4 import BeautifulSoup


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


def url_is_present(url, html, page_url):
    """Resolve relative href values before checking whether a job URL remains."""
    target = normalize_url(url)
    if not target:
        return False
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        candidate = normalize_url(urljoin(page_url, link["href"].strip()))
        if candidate == target:
            return True
    return False
