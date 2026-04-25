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


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
        return value[1:-1]
    return value
