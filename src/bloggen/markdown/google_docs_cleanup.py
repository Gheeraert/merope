"""Small cleanup helpers for Google Docs Markdown exports."""

from __future__ import annotations

# Non-breaking spaces adjacent to these are deliberate French typography
# (see bloggen.markdown.typography), not Google Docs copy-paste artifacts,
# and must survive this cleanup.
_NBSP_FOLLOWERS = ";:!?\u00bb"
_NBSP_PRECEDERS = "\u00ab"


def cleanup_google_docs_markdown(text: str) -> str:
    cleaned = _strip_utf8_bom(text)
    cleaned = _strip_stray_nbsp(cleaned)
    return cleaned


def _strip_stray_nbsp(text: str) -> str:
    result = []
    for index, char in enumerate(text):
        if char == "\u00a0":
            following = text[index + 1] if index + 1 < len(text) else ""
            preceding = text[index - 1] if index > 0 else ""
            if following in _NBSP_FOLLOWERS or preceding in _NBSP_PRECEDERS:
                result.append(char)
                continue
            result.append(" ")
        else:
            result.append(char)
    return "".join(result)


def _strip_utf8_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text
