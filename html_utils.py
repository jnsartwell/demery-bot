import asyncio
import re

import aiohttp
from bs4 import BeautifulSoup, Comment

NOISE_TAGS = {"script", "style", "noscript", "svg", "iframe", "header", "footer", "nav"}
KEEP_ATTRS = {"id", "class", "href", "src", "alt"}
BRACKET_KEYWORDS = {"bracket", "pick", "matchup", "round", "region", "seed", "tournament"}


async def fetch_html(url: str) -> str:
    """Fetch HTML from a URL. Raises ValueError on non-200, non-HTML, or timeout."""
    timeout = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DemeryBot/1.0)"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status} fetching {url}")
                content_type = resp.content_type or ""
                if "html" not in content_type:
                    raise ValueError(f"Expected HTML but got {content_type}")
                return await resp.text()
    except asyncio.TimeoutError as e:
        raise ValueError(f"Timeout fetching {url}") from e
    except aiohttp.ClientError as e:
        raise ValueError(f"Error fetching {url}: {e}") from e


def _extract_embedded_json(soup: BeautifulSoup) -> str | None:
    """Extract bracket-relevant JSON from script tags."""
    for script in soup.find_all("script"):
        text = script.string or ""
        # Check for __NEXT_DATA__ script tags (Next.js)
        if script.get("id") == "__NEXT_DATA__":
            return text.strip()
        # Check for window.__INITIAL_STATE__ or similar assignments
        for pattern in [r"window\.__INITIAL_STATE__\s*=\s*", r"window\.__NEXT_DATA__\s*=\s*"]:
            match = re.search(pattern, text)
            if match:
                # Extract from the assignment to the end, trimming trailing semicolons
                json_start = match.end()
                remainder = text[json_start:].rstrip().rstrip(";")
                return remainder
    return None


def preprocess_html(html: str, max_chars: int = 100_000) -> str:
    """
    Preprocess HTML for LLM bracket extraction.
    Strips noise, extracts embedded JSON, isolates bracket content.
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Step 1: Extract embedded JSON before stripping scripts
    embedded_json = _extract_embedded_json(soup)
    json_prefix = ""
    if embedded_json:
        json_prefix = f"EMBEDDED DATA:\n{embedded_json}\n\nHTML CONTENT:\n"

    # Step 2: Strip noise tags
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    # Step 3: Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Step 4: Strip non-semantic attributes
    for tag in soup.find_all(True):
        attrs_to_remove = [attr for attr in tag.attrs if attr not in KEEP_ATTRS]
        for attr in attrs_to_remove:
            del tag[attr]

    # Step 5: Isolate bracket subtree
    bracket_element = None
    for tag in soup.find_all(True, attrs={"id": True}):
        tag_id = (tag.get("id") or "").lower()
        if any(kw in tag_id for kw in BRACKET_KEYWORDS):
            bracket_element = tag
            break
    if not bracket_element:
        for tag in soup.find_all(True, attrs={"class": True}):
            classes = " ".join(tag.get("class", [])).lower()
            if any(kw in classes for kw in BRACKET_KEYWORDS):
                bracket_element = tag
                break

    source = bracket_element if bracket_element else soup

    # Step 6: Get text, collapse whitespace, truncate
    text = source.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()

    result = json_prefix + text
    if len(result) > max_chars:
        result = result[:max_chars]

    return result
