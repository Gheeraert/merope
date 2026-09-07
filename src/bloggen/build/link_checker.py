"""Post-build internal link/image checker.

MEROPE emits purely relative hrefs/srcs for anything internal (see
render/navigation.py's resolve_navigation_href) — this walks every
generated HTML file and confirms each one actually resolves to a real
file under output_root. Catches what nothing else in the pipeline does:
a menu target left pointing at a slug that was since renamed, a stale
link inside hand-written Markdown, or a missing image — the audit's
"aucun contrôle de doublons ou d'URL réellement produites".

External links, mailto:/tel:, anchors, and data: URIs are never
checked — only same-site references the build itself was responsible
for producing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from lxml import html

_CHECKED_ATTRS: tuple[tuple[str, str], ...] = (("a", "href"), ("img", "src"))
_SKIPPED_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")


@dataclass(slots=True, frozen=True)
class BrokenLink:
    source_file: Path
    tag: str
    attribute: str
    target: str

    def __str__(self) -> str:
        return f"{self.source_file}: <{self.tag} {self.attribute}=\"{self.target}\"> introuvable"


def _is_checkable(value: str) -> bool:
    value = value.strip()
    if not value or value.startswith("#"):
        return False
    if value.lower().startswith(_SKIPPED_SCHEMES):
        return False
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return False  # absolute external URL, or a protocol-relative //host/...
    return True


def check_broken_links(output_root: Path) -> list[BrokenLink]:
    """Every internal <a href>/<img src> in the generated site, checked
    against what's actually on disk under ``output_root``. Safe to call
    on a build that otherwise failed to reach this point — just don't."""
    broken: list[BrokenLink] = []
    for html_path in sorted(output_root.rglob("*.html")):
        try:
            text = html_path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = html.fromstring(text)
        except Exception:  # noqa: BLE001 - a malformed fragment isn't this checker's job
            continue

        for tag, attribute in _CHECKED_ATTRS:
            for element in tree.iter(tag):
                target = element.get(attribute)
                if not target or not _is_checkable(target):
                    continue
                path_part = urlsplit(target).path
                if not path_part:
                    continue
                resolved = (html_path.parent / path_part).resolve()
                if not resolved.exists():
                    broken.append(
                        BrokenLink(source_file=html_path, tag=tag, attribute=attribute, target=target)
                    )
    return broken
