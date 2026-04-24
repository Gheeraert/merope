"""Small cleanup helpers for Google Docs Markdown exports."""

from __future__ import annotations


def cleanup_google_docs_markdown(text: str) -> str:
    cleaned = _strip_utf8_bom(text)
    cleaned = cleaned.replace("\u00a0", " ")
    return cleaned


def _strip_utf8_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text
