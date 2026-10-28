"""
Web article extractor for the Universal Summarization System.
Uses httpx (already installed) + BeautifulSoup4 to extract main article content.
"""
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_MAX_CONTENT_CHARS = 12_000

# Tags that typically hold main content
_MAIN_TAGS = ["article", "main", "[role='main']", ".post-content", ".entry-content", ".article-body"]

# Tags to strip (boilerplate)
_STRIP_TAGS = [
    "nav", "header", "footer", "aside", "script", "style",
    "noscript", "iframe", "form", "button", "input", "select",
    "textarea", "advertisement", "ads", ".ad", ".ads",
    ".advertisement", ".sidebar", ".menu", ".navigation",
    ".cookie", ".popup", ".modal",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def extract_web_article(url: str) -> dict:
    """
    Fetch a URL and extract the main article content.

    Returns:
        {
          "success": bool,
          "title": str,
          "content": str,
          "url": str,
          "error": str | None
        }
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {
            "success": False,
            "title": "",
            "content": "",
            "url": url,
            "error": "beautifulsoup4 is not installed on the server.",
        }

    try:
        with httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text

    except httpx.TimeoutException:
        return {"success": False, "title": "", "content": "", "url": url,
                "error": "The page took too long to respond (timeout after 20s)."}
    except httpx.HTTPStatusError as e:
        return {"success": False, "title": "", "content": "", "url": url,
                "error": f"HTTP {e.response.status_code}: Could not access the page."}
    except Exception as e:
        return {"success": False, "title": "", "content": "", "url": url,
                "error": f"Could not fetch the page: {str(e)}"}

    try:
        soup = BeautifulSoup(html, "lxml")

        # Extract title
        title = ""
        if soup.find("title"):
            title = soup.find("title").get_text(strip=True)
        elif soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)

        # Remove boilerplate tags
        for tag_name in _STRIP_TAGS:
            for el in soup.select(tag_name):
                el.decompose()

        # Try to find main content
        content_el = None
        for selector in ["article", "main", "[role='main']",
                          ".post-content", ".entry-content", ".article-body",
                          ".content", "#content", ".story-body"]:
            content_el = soup.select_one(selector)
            if content_el:
                break

        if content_el is None:
            # Fallback: find the <div> with the most text
            divs = soup.find_all("div")
            if divs:
                content_el = max(divs, key=lambda d: len(d.get_text(strip=True)))
            else:
                content_el = soup.find("body") or soup

        # Extract clean text
        text_parts = []
        for element in content_el.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
            text = element.get_text(separator=" ", strip=True)
            if text and len(text) > 20:  # skip tiny snippets
                tag = element.name
                if tag in ("h1", "h2", "h3", "h4"):
                    text_parts.append(f"\n## {text}\n")
                else:
                    text_parts.append(text)

        content = "\n".join(text_parts)

        # Clean up excessive whitespace
        content = re.sub(r"\n{3,}", "\n\n", content).strip()

        if not content:
            # Last-resort: get all text
            content = soup.get_text(separator="\n", strip=True)
            content = re.sub(r"\n{3,}", "\n\n", content).strip()

        if not content:
            return {"success": False, "title": title, "content": "", "url": url,
                    "error": "Could not extract meaningful content from this page."}

        # Truncate if very long
        if len(content) > _MAX_CONTENT_CHARS:
            content = content[:_MAX_CONTENT_CHARS] + "\n\n[Content truncated — showing first portion]"

        return {
            "success": True,
            "title": title or url,
            "content": content,
            "url": url,
            "error": None,
        }

    except Exception as e:
        logger.error(f"Web extraction error for {url}: {e}")
        return {"success": False, "title": "", "content": "", "url": url,
                "error": f"Failed to parse page content: {str(e)}"}
