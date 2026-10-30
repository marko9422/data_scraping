
import asyncio
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


URL = "https://stoos-hotels.ch/karriere/"
# URL = "https://www.ochsen.ch/Jobs.htm"

OUTPUT_FILE = Path("scrape_output/page_ai.html")




from bs4 import BeautifulSoup, Comment


def clean_html_for_ai(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Odstránenie technických a vizuálnych elementov
    remove_tags = [
        "script", "style", "noscript", "svg", "canvas",
        "img", "picture", "video", "audio", "source",
        "track", "iframe", "object", "embed", "link", "meta",
        "header", "nav", "dialog", "button"
    ]

    for tag in soup.find_all(remove_tags):
        tag.decompose()

    # Odstránenie HTML komentárov
    for comment in soup.find_all(
        string=lambda text: isinstance(text, Comment)
    ):
        comment.extract()

    # Odstránenie nepotrebných atribútov,
    # zachovanie URL a nadpisov
    keep_attributes = {"href", "title", "aria-label"}

    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr not in keep_attributes:
                del tag.attrs[attr]

    # Odstránenie prázdnych odkazov
    for tag in soup.find_all("a"):
        if not tag.get_text(" ", strip=True) and not tag.get("title"):
            tag.decompose()

    # Odstránenie prázdnych elementov pred unwrap
    for tag in soup.find_all(["div", "span", "section", "article"]):
        if not tag.get_text(" ", strip=True) and not tag.find("a"):
            tag.decompose()

    # Odstránenie obalových značiek, ale zachovanie ich obsahu
    # Značky ako h1, h2, h3, p, a, ul a li zostanú zachované.
    for tag in soup.find_all(["div", "span", "section", "article"]):
        tag.unwrap()

    # Odstránenie prázdnych riadkov a formátovanie HTML
    return soup.prettify()


async def main():
    print(f"Sťahujem stránku: {URL}")

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        wait_until="networkidle",
        page_timeout=60000,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=URL,
            config=run_config,
        )

    if not result.success:
        print(f"Chyba pri sťahovaní: {result.error_message}")
        return

    html = result.cleaned_html or result.html

    if not html:
        print("Chyba: Stránka nevrátila HTML.")
        return

    cleaned_html = clean_html_for_ai(html)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(cleaned_html, encoding="utf-8")

    original_size = len(html.encode("utf-8"))
    cleaned_size = len(cleaned_html.encode("utf-8"))

    print("\nHotovo!")
    print(f"Výstupný súbor: {OUTPUT_FILE.resolve()}")
    print(f"Pôvodná veľkosť: {original_size:,} bajtov")
    print(f"Vyčistená veľkosť: {cleaned_size:,} bajtov")

    if original_size:
        reduction = (1 - cleaned_size / original_size) * 100
        print(f"Zmenšenie: {reduction:.1f} %")

    print(f"Počet znakov: {len(cleaned_html):,}")


if __name__ == "__main__":
    asyncio.run(main())
