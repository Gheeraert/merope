"""RSS feed and sitemap.xml generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape


@dataclass(slots=True)
class FeedItem:
    title: str
    url: str
    date: str | None
    description: str | None = None


def render_rss_feed(
    *,
    site_title: str,
    site_description: str,
    base_url: str,
    language: str,
    items: list[FeedItem],
) -> str:
    base = base_url.rstrip("/")
    entries: list[str] = []
    for item in items:
        link = f"{base}{item.url}"
        pub_date_tag = ""
        rfc822_date = _format_rfc822(item.date)
        if rfc822_date:
            pub_date_tag = f"<pubDate>{rfc822_date}</pubDate>"
        entries.append(
            "<item>"
            f"<title>{xml_escape(item.title)}</title>"
            f"<link>{xml_escape(link)}</link>"
            f"<guid>{xml_escape(link)}</guid>"
            f"{pub_date_tag}"
            f"<description>{xml_escape(item.description or '')}</description>"
            "</item>"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{xml_escape(site_title)}</title>"
        f"<link>{xml_escape(base)}</link>"
        f"<description>{xml_escape(site_description)}</description>"
        f"<language>{xml_escape(language)}</language>"
        + "".join(entries)
        + "</channel></rss>\n"
    )


def render_sitemap(*, base_url: str, urls: list[str]) -> str:
    base = base_url.rstrip("/")
    entries = "".join(f"<url><loc>{xml_escape(base + url)}</loc></url>" for url in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + entries
        + "</urlset>\n"
    )


def _format_rfc822(date: str | None) -> str | None:
    if not date:
        return None
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return format_datetime(parsed)
