"""Minimal front matter parser for Markdown files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

_FRONT_MATTER_LINE = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")


class FrontMatterParseError(ValueError):
    """Raised when front matter starts but is syntactically invalid."""


@dataclass(slots=True)
class FrontMatterResult:
    metadata: dict[str, str]
    body: str
    has_front_matter: bool


def parse_front_matter(text: str) -> FrontMatterResult:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return FrontMatterResult(metadata={}, body=text, has_front_matter=False)

    lines = normalized.split("\n")
    closing_index = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            closing_index = idx
            break

    if closing_index is None:
        raise FrontMatterParseError("Délimiteur de fin du front matter YAML manquant.")

    metadata: dict[str, str] = {}
    for line in lines[1:closing_index]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _FRONT_MATTER_LINE.match(line)
        if not match:
            raise FrontMatterParseError(f"Ligne front matter invalide: {line}")
        key = match.group(1)
        value = _strip_quotes(match.group(2).strip())
        metadata[key] = value

    body = "\n".join(lines[closing_index + 1 :])
    return FrontMatterResult(metadata=metadata, body=body, has_front_matter=True)


def read_markdown_with_front_matter(path: str | Path) -> FrontMatterResult:
    text = Path(path).read_text(encoding="utf-8")
    return parse_front_matter(text)


def format_front_matter(metadata: dict[str, str]) -> str:
    """Serialize a flat metadata mapping into a ``---`` front matter block.

    Every value is wrapped in double quotes, with ``\\`` and ``"``
    backslash-escaped (undone by :func:`_strip_quotes` on read) — a title
    or citation containing both an apostrophe and a double quote (common
    in SHS work: ""le mot 'juste'"", etc.) must round-trip byte for byte,
    not lose its double quotes. Values must not contain newlines (they
    are replaced with spaces).
    """
    lines = ["---"]
    for key, value in metadata.items():
        text = str(value).replace("\n", " ").replace("\r", " ")
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}: "{escaped}"')
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return _unescape_double_quoted(value[1:-1])
    if len(value) >= 2 and value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def _unescape_double_quoted(inner: str) -> str:
    """Reverses the ``\\\\``/``\\"`` escaping :func:`format_front_matter`
    applies before wrapping a value in double quotes."""
    result: list[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner) and inner[i + 1] in ('"', "\\"):
            result.append(inner[i + 1])
            i += 2
        else:
            result.append(ch)
            i += 1
    return "".join(result)
