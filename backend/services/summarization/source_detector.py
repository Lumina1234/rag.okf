"""
Source detection for the Universal Summarization System.
Determines whether input is a YouTube URL, web URL, document ID, or plain text.
"""
import re
from typing import Optional

# Patterns for YouTube URLs
_YOUTUBE_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})"),
]

_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


def detect_source_type(
    content: Optional[str] = None,
    url: Optional[str] = None,
    document_id: Optional[int] = None,
    input_type: str = "auto",
) -> dict:
    """
    Returns a dict with:
      source_type: "youtube" | "url" | "document" | "text"
      video_id:    str | None   (only for YouTube)
      url:         str | None   (normalised URL)
      content:     str | None   (pasted text)
      document_id: int | None
    """
    # Respect explicit overrides
    if input_type and input_type != "auto":
        return {
            "source_type": input_type,
            "video_id": _extract_youtube_id(url or content or ""),
            "url": url,
            "content": content,
            "document_id": document_id,
        }

    # 1. Document ID takes priority when provided
    if document_id is not None:
        return {
            "source_type": "document",
            "video_id": None,
            "url": None,
            "content": content,
            "document_id": document_id,
        }

    # 2. Check supplied URL field first
    candidate = url or ""
    if not candidate and content:
        # Content might be a raw URL the user pasted
        stripped = content.strip()
        if _URL_PATTERN.match(stripped) and " " not in stripped:
            candidate = stripped

    if candidate:
        video_id = _extract_youtube_id(candidate)
        if video_id:
            return {
                "source_type": "youtube",
                "video_id": video_id,
                "url": candidate,
                "content": None,
                "document_id": None,
            }
        if _URL_PATTERN.match(candidate):
            return {
                "source_type": "url",
                "video_id": None,
                "url": candidate,
                "content": content if candidate != (content or "").strip() else None,
                "document_id": None,
            }

    # 3. Plain text
    return {
        "source_type": "text",
        "video_id": None,
        "url": None,
        "content": content,
        "document_id": document_id,
    }


def _extract_youtube_id(text: str) -> Optional[str]:
    """Extract YouTube video ID from a URL string."""
    if not text:
        return None
    for pattern in _YOUTUBE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return None
