"""Navigation HTML helpers driven by JSON config menus."""

from __future__ import annotations

from html import escape
from pathlib import PurePosixPath
import posixpath
import re

from bloggen.config.models import MenuLink, SideMenuSection, SideMenuSubSection
from bloggen.render.numbering import to_letters, to_roman

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


def build_side_menu_html(sections: list[SideMenuSection], *, current_path: str = "", title: str = "") -> str:
    enabled_sections = [section for section in sections if section.enabled]
    if not enabled_sections:
        return ""

    parts = ['<aside class="side-menu side-nav" aria-label="Navigation latérale">']
    title = title.strip()
    if title:
        parts.append(f'<p class="side-menu-title">{escape(title)}</p>')
    numbered_index = 0
    for section in enabled_sections:
        enabled_children = [child for child in section.children if child.enabled]
        enabled_subsections = [sub for sub in section.subsections if sub.enabled]
        has_submenu = bool(enabled_children or enabled_subsections)
        section_class = "side-menu-section has-submenu" if has_submenu else "side-menu-section"
        parts.append(f'<section class="{section_class}">')

        section_label = section.label
        if section.numbered:
            numbered_index += 1
            section_label = f"{to_roman(numbered_index)}. {section_label}"
        parts.append(
            _render_menu_heading("h3", "side-menu-section-link", section.target, section_label, current_path)
        )

        if has_submenu:
            parts.append("<ul>")
            for child in enabled_children:
                parts.append(_render_menu_link_li(child, current_path))
            letter_index = 0
            for subsection in enabled_subsections:
                letter_index += 1
                parts.append(_render_subsection_li(subsection, letter_index, section.numbered, current_path))
            parts.append("</ul>")
        parts.append("</section>")
    parts.append("</aside>")
    return "".join(parts)


def _render_subsection_li(
    subsection: SideMenuSubSection, letter_index: int, numbered: bool, current_path: str
) -> str:
    label = subsection.label
    if numbered:
        label = f"{to_letters(letter_index)}. {label}"

    enabled_children = [child for child in subsection.children if child.enabled]
    li_class = "side-menu-subsection has-submenu" if enabled_children else "side-menu-subsection"
    parts = [
        f'<li class="{li_class}">',
        _render_menu_heading("h4", "side-menu-subsection-link", subsection.target, label, current_path),
    ]
    if enabled_children:
        parts.append("<ul>")
        for child in enabled_children:
            parts.append(_render_menu_link_li(child, current_path))
        parts.append("</ul>")
    parts.append("</li>")
    return "".join(parts)


def _render_menu_heading(tag: str, link_class: str, target: str, label: str, current_path: str) -> str:
    target = (target or "").strip()
    if not target:
        return f"<{tag}>{escape(label)}</{tag}>"

    classes = [link_class]
    if _normalize_path(target) == _normalize_path(current_path):
        classes.append("is-active")
    href = resolve_navigation_href(target, current_path=current_path)
    return f'<{tag}><a class="{" ".join(classes)}" href="{escape(href)}">{escape(label)}</a></{tag}>'


def _render_menu_link_li(item: MenuLink, current_path: str) -> str:
    classes = ["menu-item"]
    if _normalize_path(item.target) == _normalize_path(current_path):
        classes.append("is-active")
    target_attr = ' target="_blank" rel="noopener noreferrer"' if item.new_tab else ""
    href = resolve_navigation_href(item.target, current_path=current_path)
    return f'<li class="{" ".join(classes)}"><a href="{escape(href)}"{target_attr}>{escape(item.label)}</a></li>'


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
