"""Minimal, non-destructive Markdown normalization helpers."""

from __future__ import annotations

from pathlib import Path

from bloggen.markdown.google_docs_cleanup import cleanup_google_docs_markdown


def normalize_markdown_text(text: str, *, google_docs_mode: bool = True) -> str:
    value = cleanup_google_docs_markdown(text) if google_docs_mode else text
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in value.split("\n")]
    normalized = "\n".join(lines)
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def normalize_markdown_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    google_docs_mode: bool = True,
) -> str:
    source = Path(input_path)
    text = source.read_text(encoding="utf-8")
    normalized = normalize_markdown_text(text, google_docs_mode=google_docs_mode)

    destination = Path(output_path) if output_path is not None else source
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(normalized, encoding="utf-8")
    return normalized
