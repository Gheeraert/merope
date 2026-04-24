"""Minimal HTML document templates for generated pages."""

from __future__ import annotations

from datetime import datetime
from html import escape

from bloggen.config.models import ProjectConfig
from bloggen.render.navigation import build_side_menu_html, build_top_menu_html


def render_page_document(
    *,
    config: ProjectConfig,
    title: str,
    content_html: str,
    current_path: str,
) -> str:
    banner_html = _render_banner(config)
    top_menu_html = build_top_menu_html(config.menus.top, current_path=current_path)
    side_menu_html = build_side_menu_html(config.menus.side, current_path=current_path)
    footer_html = _render_footer(config)

    return (
        "<!doctype html>\n"
        f"<html lang=\"{escape(config.site.language)}\">\n"
        "  <head>\n"
        "    <meta charset=\"utf-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"    <title>{escape(title)} - {escape(config.site.title)}</title>\n"
        "    <link rel=\"stylesheet\" href=\"/static/css/site.css\">\n"
        "  </head>\n"
        "  <body>\n"
        f"    {banner_html}\n"
        f"    {top_menu_html}\n"
        "    <div class=\"page-layout\">\n"
        f"      {side_menu_html}\n"
        "      <main class=\"main-content\">\n"
        f"        {content_html}\n"
        "      </main>\n"
        "    </div>\n"
        f"    {footer_html}\n"
        "    <script src=\"/static/js/app.js\"></script>\n"
        "  </body>\n"
        "</html>\n"
    )


def render_archive_fragment(title: str, items: list[tuple[str, str]]) -> str:
    entries = "".join(
        f'<li><a href="{escape(url)}">{escape(label)}</a></li>' for label, url in items
    )
    return f"<article><h1>{escape(title)}</h1><ul>{entries}</ul></article>"


def _render_banner(config: ProjectConfig) -> str:
    if not config.banner.enabled:
        return ""
    image = escape(config.banner.image)
    link = escape(config.banner.link or "/index.html")
    alt = escape(config.banner.alt or config.site.title)
    height = max(int(config.banner.height_px), 80)
    overlay = (
        f'<div class="banner-title">{escape(config.site.title)}</div>'
        if config.banner.show_title_overlay
        else ""
    )
    return (
        f'<header class="site-banner" style="height:{height}px">'
        f'<a href="{link}"><img src="/{image}" alt="{alt}"></a>{overlay}</header>'
    )


def _render_footer(config: ProjectConfig) -> str:
    chunks: list[str] = []
    if config.footer.text:
        chunks.append(escape(config.footer.text))
    if config.footer.show_generation_info:
        chunks.append("Généré par MEROPE")
    if config.footer.show_last_build_date:
        chunks.append(datetime.now().strftime("%Y-%m-%d %H:%M"))
    if not chunks:
        return ""
    return f'<footer class="site-footer">{" | ".join(chunks)}</footer>'
