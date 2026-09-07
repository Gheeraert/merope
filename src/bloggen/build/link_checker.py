"""Post-build content-integrity checks: broken internal links/images,
orphan pages, malformed canonical URLs, invalid/incomplete structured
data (JSON-LD), and missing SEO metadata (description, H1).

MEROPE emits purely relative hrefs/srcs for anything internal (see
render/navigation.py's resolve_navigation_href) — check_broken_links
walks every generated HTML file and confirms each one actually resolves
to a real file under output_root. Catches what nothing else in the
pipeline does: a menu target left pointing at a slug that was since
renamed, a stale link inside hand-written Markdown, or a missing image —
the audit's "aucun contrôle de doublons ou d'URL réellement produites".
find_orphan_pages, check_canonical_links, check_structured_data and
check_seo_metadata extend that same after-the-fact safety net to more
ways the generated site can be quietly broken without a single file
being individually invalid.

External links, mailto:/tel:, anchors, and data: URIs are never
checked — only same-site references the build itself was responsible
for producing.
"""

from __future__ import annotations

import json
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


def _is_noindex(tree) -> bool:
    for element in tree.xpath('//meta[@name="robots"]'):
        if "noindex" in (element.get("content") or "").lower():
            return True
    return False


def find_orphan_pages(output_root: Path) -> list[Path]:
    """Every generated page with no incoming internal <a href> from
    anywhere else in the site — reachable only by knowing its URL in
    advance (typed directly, or found via the sitemap/search index), not
    by browsing. Usually a menu entry that was removed without removing
    the page it pointed at, or a page never linked from anywhere to
    begin with.

    Two kinds of page are exempt, both by design rather than oversight:
    ``/index.html`` (the site's entry point, not something anything else
    needs to link to), and any page marked noindex (currently: the
    home.source page duplicated onto /index.html when home.mode is
    "page" — see site_builder._generate_home_page/_build_single_item —
    which is deliberately never the page anything should link to; its
    canonical points at /index.html instead).
    """
    html_files = sorted(output_root.rglob("*.html"))
    linked_targets: set[Path] = set()
    trees: dict[Path, object] = {}
    for html_path in html_files:
        try:
            text = html_path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = html.fromstring(text)
        except Exception:  # noqa: BLE001 - a malformed fragment isn't this checker's job
            continue
        trees[html_path] = tree
        for element in tree.iter("a"):
            target = element.get("href")
            if not target or not _is_checkable(target):
                continue
            path_part = urlsplit(target).path
            if not path_part:
                continue
            linked_targets.add((html_path.parent / path_part).resolve())

    home_page = (output_root / "index.html").resolve()
    orphans = []
    for html_path in html_files:
        resolved = html_path.resolve()
        if resolved == home_page or resolved in linked_targets:
            continue
        tree = trees.get(html_path)
        if tree is not None and _is_noindex(tree):
            continue
        orphans.append(html_path)
    return orphans


@dataclass(slots=True, frozen=True)
class CanonicalIssue:
    source_file: Path
    canonical_url: str
    reason: str

    def __str__(self) -> str:
        return f'{self.source_file}: canonical "{self.canonical_url}" {self.reason}'


def check_canonical_links(output_root: Path, base_url: str) -> list[CanonicalIssue]:
    """Every <link rel="canonical"> in the generated site, checked
    against ``site.base_url`` and the files actually on disk.

    Skipped entirely when ``base_url`` is blank — render_page_document
    never emits a canonical link without one (see _render_seo_meta), so
    there would be nothing to check.
    """
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        return []

    issues: list[CanonicalIssue] = []
    for html_path in sorted(output_root.rglob("*.html")):
        try:
            text = html_path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = html.fromstring(text)
        except Exception:  # noqa: BLE001 - a malformed fragment isn't this checker's job
            continue

        for element in tree.xpath('//link[@rel="canonical"]'):
            href = (element.get("href") or "").strip()
            if not href:
                continue
            if href != base_url and not href.startswith(base_url + "/"):
                issues.append(
                    CanonicalIssue(html_path, href, "ne correspond pas à site.base_url configuré")
                )
                continue
            relative_path = href[len(base_url) :].lstrip("/") or "index.html"
            if not (output_root / relative_path).exists():
                issues.append(CanonicalIssue(html_path, href, "pointe vers une page introuvable"))
    return issues


@dataclass(slots=True, frozen=True)
class StructuredDataIssue:
    source_file: Path
    reason: str

    def __str__(self) -> str:
        return f"{self.source_file}: données structurées (JSON-LD) {self.reason}"


# The properties render_html_templates._render_json_ld always includes for
# each schema.org @type it emits — see that function. A missing one means
# either a real regression there, or a hand-edited custom template that
# broke the payload it's supposed to wrap.
_REQUIRED_JSON_LD_FIELDS: dict[str, tuple[str, ...]] = {
    "BlogPosting": ("headline", "url"),
    "WebSite": ("name", "url"),
}


def check_structured_data(output_root: Path) -> list[StructuredDataIssue]:
    """Every <script type="application/ld+json"> in the generated site:
    valid JSON, and carrying the properties always expected for its own
    declared @type."""
    issues: list[StructuredDataIssue] = []
    for html_path in sorted(output_root.rglob("*.html")):
        try:
            text = html_path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = html.fromstring(text)
        except Exception:  # noqa: BLE001 - a malformed fragment isn't this checker's job
            continue

        for script in tree.xpath('//script[@type="application/ld+json"]'):
            raw = script.text or ""
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                issues.append(StructuredDataIssue(html_path, f"illisibles (JSON invalide : {exc})"))
                continue
            if not isinstance(data, dict):
                issues.append(StructuredDataIssue(html_path, "invalides (un objet JSON était attendu)"))
                continue
            schema_type = data.get("@type")
            required = _REQUIRED_JSON_LD_FIELDS.get(schema_type, ())
            missing = [field for field in required if not data.get(field)]
            if missing:
                issues.append(
                    StructuredDataIssue(
                        html_path, f'de type "{schema_type}" incomplètes (manque : {", ".join(missing)})'
                    )
                )
    return issues


@dataclass(slots=True, frozen=True)
class SeoMetadataIssue:
    source_file: Path
    reason: str

    def __str__(self) -> str:
        return f"{self.source_file}: {self.reason}"


def _has_recent_posts_home_layout(tree) -> bool:
    """True for the home page rendered in "derniers billets" mode — see
    render_recent_posts_fragment, whose docstring documents that no
    page-level heading is rendered there by design (the individual post
    titles, as <h2>, identify the content instead). Detected by its own
    distinctive markup rather than by path, since a "page" mode home
    page (home.source) is a normal page with its own <h1> and must still
    be checked."""
    return bool(tree.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " recent-post ")]'))


def check_seo_metadata(output_root: Path) -> list[SeoMetadataIssue]:
    """Every generated page: a non-empty <meta name="description">, and
    exactly one <h1> — both silently degrade search-result snippets and
    heading-based SEO/accessibility signals, with nothing else in the
    pipeline surfacing a page that ends up missing either one (an empty
    ``site.description`` with no page-level override, or a custom
    template that drops the title injection)."""
    issues: list[SeoMetadataIssue] = []
    for html_path in sorted(output_root.rglob("*.html")):
        try:
            text = html_path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = html.fromstring(text)
        except Exception:  # noqa: BLE001 - a malformed fragment isn't this checker's job
            continue

        description = tree.xpath('string(//meta[@name="description"]/@content)').strip()
        if not description:
            issues.append(SeoMetadataIssue(html_path, 'aucune balise <meta name="description">'))

        h1_count = len(tree.xpath("//h1"))
        if h1_count == 0:
            if not _has_recent_posts_home_layout(tree):
                issues.append(SeoMetadataIssue(html_path, "aucun <h1>"))
        elif h1_count > 1:
            issues.append(SeoMetadataIssue(html_path, f"{h1_count} balises <h1> (une seule attendue)"))
    return issues
