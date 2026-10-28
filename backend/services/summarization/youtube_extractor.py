"""
YouTube transcript extractor for the Universal Summarization System.
Uses youtube-transcript-api (no API key required).
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Max characters we pass to the summarizer (tinyllama context limit)
_MAX_TRANSCRIPT_CHARS = 12_000


def extract_youtube_transcript(video_id: str) -> dict:
    """
    Extract the transcript for a YouTube video.

    Returns:
        {
          "success": bool,
          "title": str,
          "transcript": str,          # plain text (with timestamps)
          "with_timestamps": bool,
          "error": str | None
        }
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
        from youtube_transcript_api.formatters import TextFormatter
    except ImportError:
        return {
            "success": False,
            "title": "Unknown",
            "transcript": "",
            "with_timestamps": False,
            "error": "youtube-transcript-api is not installed on the server.",
        }

    try:
        # Prefer English, fall back to any available language
        api = YouTubeTranscriptApi()
        try:
            transcript_list = api.list(video_id)
            try:
                transcript = transcript_list.find_manually_created_transcript(["en", "en-US", "en-GB"])
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript(["en", "en-US", "en-GB"])
                except Exception:
                    # Use whatever is first available
                    transcript = list(transcript_list)[0]

            raw_entries = transcript.fetch()
        except Exception:
            # Simple fallback
            raw_entries = api.fetch(video_id)

        if not raw_entries:
            return {
                "success": False,
                "title": f"YouTube video {video_id}",
                "transcript": "",
                "with_timestamps": False,
                "error": "Transcript is empty.",
            }

        # Format with timestamps: [MM:SS] text
        lines = []
        for entry in raw_entries:
            if isinstance(entry, dict):
                start = entry.get("start", 0)
                text = entry.get("text", "").strip()
            else:
                start = getattr(entry, "start", 0)
                text = getattr(entry, "text", "").strip()

            if not text:
                continue
            minutes = int(start // 60)
            seconds = int(start % 60)
            lines.append(f"[{minutes:02d}:{seconds:02d}] {text}")

        transcript_text = "\n".join(lines)

        # Truncate if necessary
        if len(transcript_text) > _MAX_TRANSCRIPT_CHARS:
            transcript_text = transcript_text[:_MAX_TRANSCRIPT_CHARS] + "\n\n[Transcript truncated — showing first portion]"

        return {
            "success": True,
            "title": f"YouTube video (ID: {video_id})",
            "transcript": transcript_text,
            "with_timestamps": True,
            "error": None,
        }

    except Exception as e:
        err_str = str(e)
        if "TranscriptsDisabled" in err_str or "disabled" in err_str.lower():
            friendly = "Transcripts/captions are disabled for this video."
        elif "NoTranscriptFound" in err_str or "No transcripts" in err_str:
            friendly = "No transcript is available for this video."
        elif "VideoUnavailable" in err_str or "unavailable" in err_str.lower():
            friendly = "The video is unavailable or private."
        else:
            friendly = f"Could not retrieve transcript: {err_str}"

        logger.warning(f"YouTube transcript extraction failed for {video_id}: {e}")
        return {
            "success": False,
            "title": f"YouTube video (ID: {video_id})",
            "transcript": "",
            "with_timestamps": False,
            "error": friendly,
        }
