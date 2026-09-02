"""HTML document templates for generated pages."""

from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import PurePosixPath
import re
from string import Template

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
    show_title_heading: bool = False,
    description: str | None = None,
    custom_template: str | None = None,
) -> str:
    banner_html = _render_banner(config, asset_prefix=asset_prefix, current_path=current_path)
    top_menu_html = build_top_menu_html(config.menus.top, current_path=current_path)
    side_menu_html = build_side_menu_html(
        config.menus.side, current_path=current_path, title=config.menus.side_title
    )
    footer_html = _render_footer(config)
    search_html = _render_search_box(config, asset_prefix=asset_prefix)
    css_href = _asset_url("static/css/site.css", asset_prefix=asset_prefix)
    app_js_src = _asset_url("static/js/app.js", asset_prefix=asset_prefix)
    lightbox_js_src = _asset_url("static/js/lightbox.js", asset_prefix=asset_prefix)
    search_js_src = _asset_url("static/js/search.js", asset_prefix=asset_prefix)
    seo_html = _render_seo_meta(
        config,
        title=title,
        current_path=current_path,
        description=description,
        is_article=bool(article_date),
        published_date=article_date,
    )

    side_class = "has-side-menu" if side_menu_html else "no-side-menu"
    lightbox_enabled_attr = "1" if config.render.enable_lightbox else "0"
    # Search sits at the end of the top menu's own black bar rather than as
    # a separate strip below it — one shared row, only built when at least
    # one of the two is actually present.
    masthead_parts = [part for part in (top_menu_html, search_html) if part]
    masthead_html = f'<div class="masthead">{"".join(masthead_parts)}</div>' if masthead_parts else ""

    scripts = [f'    <script src="{escape(app_js_src)}"></script>']
    if config.render.enable_lightbox:
        scripts.append(f'    <script src="{escape(lightbox_js_src)}"></script>')
    if config.search.enabled:
        scripts.append(f'    <script src="{escape(search_js_src)}"></script>')

    normalized_content = content_html
    if suppress_fragment_meta:
        normalized_content = _strip_fragment_article_meta(normalized_content)
    if article_date:
        normalized_content = _inject_article_date(normalized_content, article_date)
    if show_title_heading:
        normalized_content = _inject_article_title(normalized_content, title)

    if custom_template:
        return Template(custom_template).safe_substitute(
            lang=config.site.language,
            title=escape(title),
            site_title=escape(config.site.title),
            seo_meta=seo_html,
            css_href=escape(css_href),
            lightbox_enabled=lightbox_enabled_attr,
            banner=banner_html,
            top_menu=top_menu_html,
            side_menu=side_menu_html,
            side_class=side_class,
            content=normalized_content,
            footer=footer_html,
            search=search_html,
            scripts="\n".join(scripts),
        )

    return (
        "<!doctype html>\n"
        f"<html lang=\"{escape(config.site.language)}\">\n"
        "  <head>\n"
        "    <meta charset=\"utf-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"    <title>{escape(title)} · {escape(config.site.title)}</title>\n"
        f"{seo_html}"
        f"    <link rel=\"stylesheet\" href=\"{escape(css_href)}\">\n"
        "  </head>\n"
        f"  <body data-lightbox-enabled=\"{lightbox_enabled_attr}\">\n"
        f"    {banner_html}\n"
        f"    {masthead_html}\n"
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


def render_external_link_fragment(*, label: str, url: str) -> str:
    """Content for the wrapper page generated for a "lien externe" menu entry.

    Embeds the external URL in an ``<iframe>`` so the site's own banner/menus
    stay visible around it, instead of navigating away. Not every external
    site allows this (``X-Frame-Options``/CSP can refuse to be framed), so a
    plain fallback link is always shown above the frame.
    """
    escaped_url = escape(url)
    return (
        '<div class="external-embed">'
        '<p class="external-embed-notice">Contenu externe : '
        f'<a href="{escaped_url}" target="_blank" rel="noopener noreferrer">{escaped_url}</a>'
        "</p>"
        f'<iframe class="external-embed-frame" src="{escaped_url}" title="{escape(label)}" loading="lazy"></iframe>'
        "</div>"
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


def _render_search_box(config: ProjectConfig, *, asset_prefix: str) -> str:
    if not config.search.enabled:
        return ""
    index_href = _asset_url("search-index.json", asset_prefix=asset_prefix)
    prefix = (asset_prefix or ".").replace("\\", "/")
    return (
        f'<div class="site-search" data-index-href="{escape(index_href)}" '
        f'data-asset-prefix="{escape(prefix)}">'
        '<input type="search" class="site-search-input" placeholder="Rechercher…" '
        'aria-label="Rechercher sur le site">'
        '<ul class="site-search-results" hidden></ul>'
        "</div>"
    )


def _render_seo_meta(
    config: ProjectConfig,
    *,
    title: str,
    current_path: str,
    description: str | None,
    is_article: bool = False,
    published_date: str | None = None,
) -> str:
    meta_description = (description or config.site.description or "").strip()
    base_url = (config.site.base_url or "").strip()
    canonical_url = f"{base_url.rstrip('/')}{current_path}" if base_url else None
    author = (config.site.author or "").strip()

    lines: list[str] = []
    if meta_description:
        lines.append(f'    <meta name="description" content="{escape(meta_description)}">')
    if author:
        lines.append(f'    <meta name="author" content="{escape(author)}">')
    if canonical_url:
        lines.append(f'    <link rel="canonical" href="{escape(canonical_url)}">')

    lines.append(f'    <meta property="og:title" content="{escape(title)}">')
    lines.append(f'    <meta property="og:type" content="{"article" if is_article else "website"}">')
    if meta_description:
        lines.append(f'    <meta property="og:description" content="{escape(meta_description)}">')
    if canonical_url:
        lines.append(f'    <meta property="og:url" content="{escape(canonical_url)}">')
    if is_article and published_date:
        lines.append(
            f'    <meta property="article:published_time" content="{escape(published_date)}T00:00:00Z">'
        )
    if is_article and author:
        lines.append(f'    <meta property="article:author" content="{escape(author)}">')

    image_url = None
    image = (config.banner.image or "").strip()
    if base_url and image and not (_URI_SCHEME_RE.match(image) or image.startswith("//")):
        image_url = f"{base_url.rstrip('/')}/{image.lstrip('/')}"
        lines.append(f'    <meta property="og:image" content="{escape(image_url)}">')

    lines.append('    <meta name="twitter:card" content="summary_large_image">')
    lines.append(f'    <meta name="twitter:title" content="{escape(title)}">')
    if meta_description:
        lines.append(f'    <meta name="twitter:description" content="{escape(meta_description)}">')
    if image_url:
        lines.append(f'    <meta name="twitter:image" content="{escape(image_url)}">')

    json_ld = _render_json_ld(
        config,
        title=title,
        meta_description=meta_description,
        canonical_url=canonical_url,
        current_path=current_path,
        is_article=is_article,
        published_date=published_date,
        author=author,
    )
    if json_ld:
        lines.append(json_ld)

    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _render_json_ld(
    config: ProjectConfig,
    *,
    title: str,
    meta_description: str,
    canonical_url: str | None,
    current_path: str,
    is_article: bool,
    published_date: str | None,
    author: str,
) -> str:
    if is_article and canonical_url:
        data: dict[str, object] = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "url": canonical_url,
        }
        if meta_description:
            data["description"] = meta_description
        if published_date:
            data["datePublished"] = f"{published_date}T00:00:00Z"
        if author:
            data["author"] = {"@type": "Person", "name": author}
    elif current_path == "/index.html" and canonical_url:
        data = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": config.site.title,
            "url": canonical_url,
        }
        if meta_description:
            data["description"] = meta_description
    else:
        return ""

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'    <script type="application/ld+json">{payload}</script>'


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


def _inject_article_title(content_html: str, title: str) -> str:
    """Show the billet/page title (from its metadata) as a heading in the body.

    Rendered as H2 by default. If the content already has its own H1 (a
    top-level TEI div heading, per the XSLT's div-nesting-to-heading-level
    mapping), using H2 for the title would rank it below that internal
    heading — so the title takes H1 instead in that case, leaving the
    internal heading levels untouched.
    """
    title_value = (title or "").strip()
    if not title_value:
        return content_html
    heading_tag = "h1" if re.search(r"<h1[\s>]", content_html, flags=re.IGNORECASE) else "h2"
    title_html = f'<{heading_tag} class="article-title">{escape(title_value)}</{heading_tag}>'
    article_open = re.compile(r"(<article\b[^>]*>)", flags=re.IGNORECASE)
    if article_open.search(content_html):
        return article_open.sub(rf"\1{title_html}", content_html, count=1)
    return f"{title_html}{content_html}"
