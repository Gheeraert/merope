"""HTML document templates for generated pages."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import PurePosixPath
import re

from bloggen.config.models import ProjectConfig
from bloggen.render.navigation import (
    build_side_menu_html,
    build_top_menu_html,
    resolve_navigation_href,
)

_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def render_page_document(
    *,
    config: ProjectConfig,
    title: str,
    content_html: str,
    current_path: str,
    asset_prefix: str,
    article_date: str | None = None,
    suppress_fragment_meta: bool = False,
) -> str:
    banner_html = _render_banner(config, asset_prefix=asset_prefix, current_path=current_path)
    top_menu_html = build_top_menu_html(config.menus.top, current_path=current_path)
    side_menu_html = build_side_menu_html(config.menus.side, current_path=current_path)
    footer_html = _render_footer(config)
    css_href = _asset_url("static/css/site.css", asset_prefix=asset_prefix)
    app_js_src = _asset_url("static/js/app.js", asset_prefix=asset_prefix)
    lightbox_js_src = _asset_url("static/js/lightbox.js", asset_prefix=asset_prefix)

    side_class = "has-side-menu" if side_menu_html else "no-side-menu"
    lightbox_enabled_attr = "1" if config.render.enable_lightbox else "0"

    scripts = [f'    <script src="{escape(app_js_src)}"></script>']
    if config.render.enable_lightbox:
        scripts.append(f'    <script src="{escape(lightbox_js_src)}"></script>')

    normalized_content = content_html
    if suppress_fragment_meta:
        normalized_content = _strip_fragment_article_meta(normalized_content)
    if article_date:
        normalized_content = _inject_article_date(normalized_content, article_date)

    return (
        "<!doctype html>\n"
        f"<html lang=\"{escape(config.site.language)}\">\n"
        "  <head>\n"
        "    <meta charset=\"utf-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"    <title>{escape(title)} · {escape(config.site.title)}</title>\n"
        f"    <link rel=\"stylesheet\" href=\"{escape(css_href)}\">\n"
        "  </head>\n"
        f"  <body data-lightbox-enabled=\"{lightbox_enabled_attr}\">\n"
        f"    {banner_html}\n"
        f"    {top_menu_html}\n"
        f"    <div class=\"page-layout {side_class}\">\n"
        f"      {side_menu_html}\n"
        "      <main class=\"main-content article-content\">\n"
        f"        {normalized_content}\n"
        "      </main>\n"
        "    </div>\n"
        f"    {footer_html}\n"
        + "\n".join(scripts)
        + "\n  </body>\n"
        "</html>\n"
    )


def render_archive_fragment(
    title: str,
    items: list[tuple[str, str] | tuple[str, str, str | None]],
    *,
    current_path: str,
) -> str:
    if items:
        entries_parts: list[str] = []
        for item in items:
            label, url, date = _normalize_archive_item(item)
            resolved = resolve_navigation_href(url, current_path=current_path)
            date_html = (
                f'<time class="archive-date" datetime="{escape(date)}">{escape(date)}</time>'
                if date
                else ""
            )
            entries_parts.append(
                '<li class="archive-item">'
                f'<a class="archive-link" href="{escape(resolved)}">{escape(label)}</a>'
                f"{date_html}</li>"
            )
        entries = "".join(entries_parts)
    else:
        entries = '<li class="archive-empty">Aucun billet publié.</li>'

    return (
        '<article class="archive-page">'
        f"<h1>{escape(title)}</h1>"
        f'<ul class="archive-list">{entries}</ul>'
        "</article>"
    )


def _normalize_archive_item(
    item: tuple[str, str] | tuple[str, str, str | None],
) -> tuple[str, str, str | None]:
    if len(item) == 2:
        label, url = item
        return label, url, None

    label, url, date = item
    normalized_date = (date or "").strip() or None
    return label, url, normalized_date


def _render_banner(config: ProjectConfig, *, asset_prefix: str, current_path: str) -> str:
    if not config.banner.enabled:
        return ""
    image = _asset_url(config.banner.image, asset_prefix=asset_prefix)
    link = resolve_navigation_href(config.banner.link or "/index.html", current_path=current_path)
    if not image:
        return ""
    alt = escape(config.banner.alt or config.site.title)
    height = max(int(config.banner.height_px), 80)
    overlay = (
        f'<div class="banner-title">{escape(config.site.title)}</div>'
        if config.banner.show_title_overlay
        else ""
    )
    return (
        f'<header class="site-banner" style="height:{height}px">'
        f'<a href="{link}"><img src="{escape(image)}" alt="{alt}"></a>{overlay}</header>'
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


def _asset_url(path: str, *, asset_prefix: str) -> str:
    value = (path or "").strip()
    if not value:
        return ""

    if _URI_SCHEME_RE.match(value) or value.startswith("//"):
        return value

    prefix = (asset_prefix or ".").replace("\\", "/")
    if prefix == ".":
        prefix = ""

    normalized = value.lstrip("/")
    if not prefix:
        return normalized

    return str(PurePosixPath(prefix) / normalized)


def _strip_fragment_article_meta(content_html: str) -> str:
    return re.sub(
        r'<header class="article-header">.*?</header>\s*',
        "",
        content_html,
        count=1,
        flags=re.DOTALL,
    )


def _inject_article_date(content_html: str, article_date: str) -> str:
    date_value = article_date.strip()
    if not date_value:
        return content_html
    escaped_date = escape(date_value)
    meta_html = (
        '<header class="article-header article-header--metadata">'
        '<p class="article-meta">'
        f'<time datetime="{escaped_date}">{escaped_date}</time>'
        "</p>"
        "</header>"
    )
    article_open = re.compile(r"(<article\b[^>]*>)", flags=re.IGNORECASE)
    if article_open.search(content_html):
        return article_open.sub(rf"\1{meta_html}", content_html, count=1)
    return f"{meta_html}{content_html}"
