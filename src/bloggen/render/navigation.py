"""Navigation HTML helpers driven by JSON config menus."""

from __future__ import annotations

from html import escape

from bloggen.config.models import MenuLink, SideMenuSection


def build_top_menu_html(items: list[MenuLink], *, current_path: str = "") -> str:
    enabled = [item for item in items if item.enabled]
    if not enabled:
        return ""

    parts = ["<nav class=\"top-menu\"><ul>"]
    for item in enabled:
        classes = ["menu-item"]
        if _normalize_path(item.target) == _normalize_path(current_path):
            classes.append("is-active")
        target_attr = ' target="_blank" rel="noopener noreferrer"' if item.new_tab else ""
        parts.append(
            f'<li class="{" ".join(classes)}"><a href="{escape(item.target)}"{target_attr}>{escape(item.label)}</a></li>'
        )
    parts.append("</ul></nav>")
    return "".join(parts)


def build_side_menu_html(sections: list[SideMenuSection], *, current_path: str = "") -> str:
    enabled_sections = [section for section in sections if section.enabled]
    if not enabled_sections:
        return ""

    parts = ["<aside class=\"side-menu\">"]
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
                parts.append(
                    f'<li class="{" ".join(classes)}"><a href="{escape(child.target)}"{target_attr}>{escape(child.label)}</a></li>'
                )
            parts.append("</ul>")
        parts.append("</section>")
    parts.append("</aside>")
    return "".join(parts)


def _normalize_path(path: str) -> str:
    return path.strip() or "/"
