"""Navigation HTML helpers driven by JSON config menus."""

from __future__ import annotations

from html import escape
from pathlib import PurePosixPath
import posixpath
import re

from bloggen.config.models import MenuLink, SideMenuSection

_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def build_top_menu_html(items: list[MenuLink], *, current_path: str = "") -> str:
    enabled = [item for item in items if item.enabled]
    if not enabled:
        return ""

    parts = ['<nav class="top-menu top-nav" aria-label="Navigation principale"><ul>']
    for item in enabled:
        classes = ["menu-item"]
        if _normalize_path(item.target) == _normalize_path(current_path):
            classes.append("is-active")
        target_attr = ' target="_blank" rel="noopener noreferrer"' if item.new_tab else ""
        href = resolve_navigation_href(item.target, current_path=current_path)
        parts.append(
            f'<li class="{" ".join(classes)}"><a href="{escape(href)}"{target_attr}>{escape(item.label)}</a></li>'
        )
    parts.append("</ul></nav>")
    return "".join(parts)


def build_side_menu_html(sections: list[SideMenuSection], *, current_path: str = "") -> str:
    enabled_sections = [section for section in sections if section.enabled]
    if not enabled_sections:
        return ""

    parts = ['<aside class="side-menu side-nav" aria-label="Navigation latérale">']
    for section in enabled_sections:
        parts.append('<section class="side-menu-section">')
        parts.append(f"<h3>{escape(section.label)}</h3>")
        enabled_children = [child for child in section.children if child.enabled]
        if enabled_children:
            parts.append("<ul>")
            for child in enabled_children:
                classes = ["menu-item"]
                if _normalize_path(child.target) == _normalize_path(current_path):
                    classes.append("is-active")
                target_attr = ' target="_blank" rel="noopener noreferrer"' if child.new_tab else ""
                href = resolve_navigation_href(child.target, current_path=current_path)
                parts.append(
                    f'<li class="{" ".join(classes)}"><a href="{escape(href)}"{target_attr}>{escape(child.label)}</a></li>'
                )
            parts.append("</ul>")
        parts.append("</section>")
    parts.append("</aside>")
    return "".join(parts)


def resolve_navigation_href(target: str, *, current_path: str) -> str:
    value = (target or "").strip()
    if not value:
        return "#"
    if _is_non_internal(value):
        return value
    if not value.startswith("/"):
        return value

    current_file = _current_file_for_path(current_path)
    current_dir = current_file.parent
    destination = PurePosixPath(value.lstrip("/"))
    relative = posixpath.relpath(str(destination), start=str(current_dir))
    return relative


def _normalize_path(path: str) -> str:
    normalized = (path or "").strip()
    if not normalized:
        return "/"

    normalized = normalized.replace("\\", "/")
    if not normalized.startswith("/"):
        normalized = "/" + normalized

    if normalized.endswith("/index.html"):
        normalized = normalized[: -len("index.html")]
    if normalized.endswith("/") and normalized != "/":
        normalized = normalized.rstrip("/")

    return normalized


def _is_non_internal(value: str) -> bool:
    if value.startswith(("#", "//")):
        return True
    if value.startswith("mailto:"):
        return True
    return bool(_URI_SCHEME_RE.match(value))


def _current_file_for_path(current_path: str) -> PurePosixPath:
    normalized = (current_path or "").strip().replace("\\", "/")
    if not normalized or normalized == "/":
        return PurePosixPath("index.html")

    if normalized.startswith("/"):
        normalized = normalized[1:]
    if normalized.endswith("/"):
        normalized = f"{normalized}index.html"

    path = PurePosixPath(normalized)
    if path.suffix:
        return path
    return path / "index.html"
