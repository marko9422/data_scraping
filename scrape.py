import asyncio
import difflib
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


PROJECT_DIR = Path(__file__).resolve().parent
SITES_FILE = PROJECT_DIR / "sites.json"
OUTPUT_DIR = PROJECT_DIR / "scrape_output"


def load_sites():
    """Load and validate websites from sites.json."""
    if not SITES_FILE.exists():
        raise FileNotFoundError(f"Configuration file not found: {SITES_FILE}")

    with SITES_FILE.open("r", encoding="utf-8") as file:
        sites = json.load(file)

    if not isinstance(sites, list) or not sites:
        raise ValueError("sites.json must contain a non-empty list.")

    for site in sites:
        if not isinstance(site, dict) or not site.get("name") or not site.get("url"):
            raise ValueError("Every website needs 'name' and 'url'.")

    return sites


def make_filename(site):
    """Create a safe filename for each website."""
    slug = site.get("slug") or site["name"].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"{slug or 'website'}.html"


def clean_html(html):
    """Remove technical noise while preserving readable content and links."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all([
        "script", "style", "noscript", "svg", "canvas",
        "img", "picture", "video", "audio", "source", "track",
        "iframe", "object", "embed"
    ]):
        tag.decompose()

    for comment in soup.find_all(
        string=lambda value: isinstance(value, Comment)
    ):
        comment.extract()

    allowed_attributes = {"href", "title", "aria-label", "datetime"}

    for tag in soup.find_all(True):
        tag.attrs = {
            name: value
            for name, value in tag.attrs.items()
            if name in allowed_attributes
        }

    # Remove empty containers, but retain containers holding linked content.
    for tag in soup.find_all(["div", "span", "section", "article"]):
        if (
            not tag.get_text(" ", strip=True)
            and not tag.find("a", href=True)
        ):
            tag.decompose()

    # Unwrap generic layout elements; their contents remain.
    for tag in soup.find_all(["div", "span", "section", "article"]):
        tag.unwrap()

    # Remove empty paragraphs and links without destinations.
    for tag in soup.find_all(["p", "a"]):
        if not tag.get_text(" ", strip=True):
            if tag.name == "a" and tag.get("href"):
                continue
            tag.decompose()

    return soup.prettify()


def print_html_diff(old_html, new_html, filename):
    """Print a unified diff showing exactly which lines changed."""
    old_lines = old_html.splitlines()
    new_lines = new_html.splitlines()

    diff = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"previous/{filename}",
        tofile=f"current/{filename}",
        lineterm="",
        n=3,
    ))

    added = sum(
        1 for line in diff
        if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff
        if line.startswith("-") and not line.startswith("---")
    )

    print("\n" + "=" * 70)
    print(f"CHANGES IN: {filename}")
    print(f"Lines added: {added} | Lines removed: {removed}")
    print("=" * 70)

    if diff:
        print("\n".join(diff))
    else:
        print("No line-level differences found.")

    print("=" * 70 + "\n")


def compare_and_save(output_file, new_html):
    """
    Compare the new HTML with the saved version.

    First run: save as NEW.
    Same content: keep existing file.
    Changed content: print differences, then replace existing file.
    """
    if not output_file.exists():
        output_file.write_text(new_html, encoding="utf-8")
        return "NEW"

    old_html = output_file.read_text(encoding="utf-8")

    if old_html == new_html:
        return "UNCHANGED"

    # Show the exact differences before replacing the old version.
    print_html_diff(old_html, new_html, output_file.name)

    output_file.write_text(new_html, encoding="utf-8")
    return "CHANGED"


async def scrape_site(crawler, site, run_config):
    """Scrape, clean, compare and save one website."""
    name = site["name"]
    url = site["url"]
    output_file = OUTPUT_DIR / make_filename(site)

    print(f"\nScraping: {name}")
    print(f"URL: {url}")

    try:
        result = await crawler.arun(url=url, config=run_config)

        if not result.success:
            print(f"FAILED: {result.error_message}")
            return False

        html = result.html or result.cleaned_html
        if not html:
            print("FAILED: The page returned empty HTML.")
            return False

        cleaned = clean_html(html)
        status = compare_and_save(output_file, cleaned)

        if status == "NEW":
            print("NEW: First scrape. HTML saved.")
        elif status == "UNCHANGED":
            print("UNCHANGED: Nothing changed. HTML is identical.")
        else:
            print("CHANGED: Differences printed above. Saved the new HTML.")

        original_size = len(html.encode("utf-8"))
        cleaned_size = len(cleaned.encode("utf-8"))
        reduction = (
            (1 - cleaned_size / original_size) * 100
            if original_size else 0
        )
        link_count = len(
            BeautifulSoup(cleaned, "html.parser").find_all("a", href=True)
        )

        print(f"File: {output_file.relative_to(PROJECT_DIR)}")
        print(f"Original size: {original_size:,} bytes")
        print(f"Cleaned size: {cleaned_size:,} bytes")
        print(f"Size reduction: {reduction:.1f}%")
        print(f"Links preserved: {link_count}")

        return True

    except Exception as error:
        print(f"ERROR while scraping {name}: {error}")
        return False


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sites = load_sites()

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        wait_until="networkidle",
        page_timeout=60000,
    )

    successful = 0

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for site in sites:
            if await scrape_site(crawler, site, run_config):
                successful += 1

    print("\nScraping finished.")
    print(f"Successful: {successful}/{len(sites)}")
    print(f"Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
