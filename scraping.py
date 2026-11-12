"""Download and clean HTML without site-specific selectors."""
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup, Comment


def load_sites(config_path):
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing config: {path}")
    sites = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(sites, list) or not sites:
        raise ValueError("sites.json must contain a non-empty list")
    for site in sites:
        if not isinstance(site, dict) or not site.get("name") or not site.get("url"):
            raise ValueError("Every site needs name and url")
        site.setdefault("slug", "")
        site.setdefault("address", "")
        site.setdefault("canton", "")
    return sites


def make_filename(site):
    slug = site.get("slug") or site["name"].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return (slug or "website") + ".html"


def clean_html(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup.find_all([
        "script", "style", "noscript", "svg", "canvas", "img", "picture",
        "video", "audio", "source", "track", "iframe", "object", "embed",
    ]):
        tag.decompose()
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()

    # Keep links and DOM containers; AI needs hrefs and surrounding context.
    keep = {"href", "title", "datetime", "aria-label"}
    for tag in soup.find_all(True):
        tag.attrs = {key: value for key, value in tag.attrs.items() if key in keep}

    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        if not tag.get_text(" ", strip=True) and not tag.find("a", href=True):
            if tag.name not in {"html", "body", "main"}:
                tag.decompose()
    return soup.prettify()


async def fetch_and_clean_page(crawler, url, config):
    result = await crawler.arun(url=url, config=config)
    if not result.success:
        raise RuntimeError(result.error_message or "Crawl failed: " + url)
    raw = result.html or result.cleaned_html
    if not raw or len(raw.strip()) < 100:
        raise RuntimeError("Page is empty or suspiciously short: " + url)
    return clean_html(raw)
