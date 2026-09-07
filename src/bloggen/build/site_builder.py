"""Static site builder for MEROPE V1."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import shutil
import time
import uuid

from bloggen.build.assets import (
    copy_linked_content_assets,
    copy_project_assets,
    copy_theme_resources,
)
from bloggen.build.link_checker import check_broken_links
from bloggen.build.redirects import (
    load_url_history,
    plan_redirects,
    render_redirect_html,
    save_url_history,
    update_history,
)
from bloggen.build.reports import BuildReport
from bloggen.config.models import MenuLink, ProjectConfig, SideMenuSection, SideMenuSubSection
from bloggen.content.loader import ContentItem, ContentLoadError, LoadedContent, load_content
from bloggen.content.slugify import ensure_unique_slug, slugify
from bloggen.render.feeds import FeedItem, render_robots_txt, render_rss_feed, render_sitemap
from bloggen.render.html_templates import (
    render_archive_fragment,
    render_external_link_fragment,
    render_page_document,
    render_recent_posts_fragment,
)
from bloggen.render.theme import load_custom_template
from bloggen.render.lightbox import apply_lightbox_markup
from bloggen.render.margin_notes import apply_notes_rendering
from bloggen.render.search_index import SearchEntry, extract_plain_text, render_search_index
from bloggen.render.xslt_runner import render_tei_file_to_html_fragment
from bloggen.tei.pandoc_converter import PandocUnavailableError, convert_markdown_file_to_tei
from bloggen.tei.postprocess import rewrite_graphic_urls_in_tei_file
from bloggen.content.loader import ContentItem, LoadedContent, load_content

_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(slots=True)
class GeneratedItem:
    source: Path
    title: str
    slug: str
    url: str
    html_path: Path
    tei_path: Path
    date: str | None
    content_html: str
    description: str | None
    # The source .md file's own last-modified date (falls back to `date`
    # when the file can't be stat'd) — used for sitemap <lastmod>, which
    # previously always used the *publication* date, even for a page
    # with no date field at all (any page: only posts require one) or a
    # post edited long after its original publication.
    lastmod: str | None = None
    # True for a page whose content is duplicated onto another indexable
    # URL — currently only the page configured as home.source when
    # home.mode is "page" (see _generate_home_page): its content is
    # rendered again at /index.html, which stays the one canonical,
    # indexable copy.
    noindex: bool = False


def _critical_project_dirs(config: ProjectConfig, project_root: Path) -> dict[str, Path]:
    """The project's own root plus every source directory a build reads
    from — none of these may ever be wiped by the output-dir cleanup.
    """
    paths = config.paths
    relative_by_label = {
        "la racine du projet": Path("."),
        "le dossier contenu": paths.content_dir,
        "le dossier des pages": paths.pages_dir,
        "le dossier des billets": paths.posts_dir,
        "le dossier assets": paths.assets_dir,
        "le dossier thème": paths.theme_dir,
        "le dossier templates": paths.templates_dir,
        "le dossier XSLT": paths.xslt_dir,
    }
    return {label: (project_root / relative).resolve() for label, relative in relative_by_label.items()}


def _ensure_output_dir_is_safe_to_clean(output_root: Path, project_root: Path, config: ProjectConfig) -> None:
    """Refuse to ``shutil.rmtree`` a directory that *is*, or *contains*,
    the project root or any of its source directories.

    ``paths.output_dir`` is a free-text field editable from the "Chemins"
    tab; a careless value (``.``, ``..``, or simply the same folder as
    ``content_dir``) would otherwise silently delete the whole project —
    or its source content — the next time "Générer le site" runs with
    "Nettoyer le dossier de sortie" enabled.

    It must also stay *inside* the project: ``project_root / output_dir``
    silently discards ``project_root`` when ``output_dir`` is an absolute
    path (e.g. ``C:/Users/alice/Documents``), and an ``output_dir`` such as
    ``../../Documents`` escapes via ``..`` — either way an unrelated,
    possibly non-empty folder outside the project would be wiped out
    without warning.
    """
    if output_root != project_root and project_root not in output_root.parents:
        raise ValueError(
            f"Dossier de sortie dangereux : « {config.paths.output_dir} » "
            f"({output_root}) est situé hors du projet ({project_root}). "
            "Utilisez un chemin relatif contenu dans le dossier du projet "
            "(ex. « site ») dans l'onglet Chemins avant de régénérer le site."
        )

    for label, path in _critical_project_dirs(config, project_root).items():
        if output_root == path or output_root in path.parents:
            raise ValueError(
                f"Dossier de sortie dangereux : « {config.paths.output_dir} » "
                f"({output_root}) supprimerait {label} ({path}). "
                "Corrigez le champ « Dossier sortie » dans l'onglet Chemins avant "
                "de régénérer le site."
            )


def _replace_directory(staging: Path, final: Path, *, attempts: int = 5) -> None:
    """Swap ``staging`` in for ``final``, retrying briefly on Windows.

    A directory that was just written to can be transiently locked by
    Windows Defender / the search indexer scanning the new files, which
    makes ``shutil.rmtree``/``Path.rename`` fail with ``PermissionError``
    (WinError 5) even though nothing is actually still using the files a
    moment later — observed intermittently in practice, not just in
    theory.
    """
    delay = 0.1
    for attempt in range(attempts):
        try:
            if final.exists():
                shutil.rmtree(final)
            staging.rename(final)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


def build_site(config: ProjectConfig, *, config_path: Path | None = None) -> BuildReport:
    project_root = resolve_project_root(config, config_path)
    runtime_config = copy.deepcopy(config)
    final_output_root = (project_root / config.paths.output_dir).resolve()
    requested_tei_root = (project_root / config.paths.tei_dir).resolve()

    report = BuildReport(success=False, output_dir=final_output_root, tei_dir=requested_tei_root)

    # When cleaning is enabled, generate into a fresh sibling directory and
    # swap it in atomically only once the whole build succeeds. Wiping
    # final_output_root up front (the previous behaviour) destroyed the
    # last good site the instant a later page/post failed to render,
    # leaving nothing publishable until the next successful build.
    staging_root: Path | None = None

    try:
        if config.build.clean_output_dir:
            if final_output_root.exists():
                _ensure_output_dir_is_safe_to_clean(final_output_root, project_root, config)
            staging_root = final_output_root.parent / (
                f".{final_output_root.name}.building-{uuid.uuid4().hex}"
            )
            staging_root.mkdir(parents=True, exist_ok=True)
            output_root = staging_root
        else:
            final_output_root.mkdir(parents=True, exist_ok=True)
            output_root = final_output_root

        _guard_banner_asset(runtime_config, project_root=project_root, report=report)
        _generate_external_link_pages(
            runtime_config, project_root=project_root, output_root=output_root, report=report
        )

        temporary_tei_root = output_root / "_tmp_tei_runtime"
        tei_root = requested_tei_root if runtime_config.render.generate_tei_files else temporary_tei_root
        tei_root.mkdir(parents=True, exist_ok=True)

        loaded = load_content(project_root, runtime_config)
        report.warnings.extend(loaded.warnings)

        generated_pages = _generate_pages(
            loaded,
            config=runtime_config,
            project_root=project_root,
            output_root=output_root,
            tei_root=tei_root,
            report=report,
        )
        if runtime_config.blog.enabled:
            generated_posts = _generate_posts(
                loaded,
                config=runtime_config,
                project_root=project_root,
                output_root=output_root,
                tei_root=tei_root,
                report=report,
            )
        else:
            # "Activer blog" off means no blog content anywhere (its own
            # tooltip: "aucune page de blog ni d'archive n'est générée") —
            # not just no archive/RSS page, so posts must not be rendered,
            # indexed for search, or listed in the sitemap either.
            generated_posts = []

        _generate_home_page(
            generated_pages,
            generated_posts,
            config=runtime_config,
            project_root=project_root,
            output_root=output_root,
            report=report,
        )
        archive_sitemap_entries = _generate_archive_page(
            generated_posts,
            config=runtime_config,
            project_root=project_root,
            output_root=output_root,
            report=report,
        )

        _generate_feed_and_sitemap(
            generated_pages,
            generated_posts,
            archive_sitemap_entries,
            config=runtime_config,
            output_root=output_root,
            report=report,
        )

        _generate_search_index(
            generated_pages,
            generated_posts,
            config=runtime_config,
            output_root=output_root,
            report=report,
        )

        redirect_history_path = project_root / ".merope-redirects.json"
        pending_redirect_history = _generate_redirects(
            generated_pages,
            generated_posts,
            config=runtime_config,
            project_root=project_root,
            output_root=output_root,
            report=report,
        )

        copied_assets = 0
        if runtime_config.build.copy_assets:
            copied_assets = copy_project_assets(project_root, runtime_config.paths.assets_dir, output_root)
        copied_resources = copy_theme_resources(project_root, runtime_config.paths.theme_dir, output_root)

        report.warnings.append(f"Ressources intégrées copiées: {copied_resources}.")
        if runtime_config.build.copy_assets:
            report.warnings.append(f"Assets globaux copiés: {copied_assets}.")

        if not runtime_config.render.generate_tei_files and temporary_tei_root.exists():
            shutil.rmtree(temporary_tei_root, ignore_errors=True)

        if runtime_config.build.check_broken_links:
            broken_links = check_broken_links(output_root)
            if broken_links:
                message = f"Liens/médias internes cassés ({len(broken_links)}) :"
                shown = broken_links[:20]
                message += "".join(f"\n  - {item}" for item in shown)
                if len(broken_links) > len(shown):
                    message += f"\n  … et {len(broken_links) - len(shown)} de plus."
                if runtime_config.build.fail_on_broken_links:
                    report.errors.append(message)
                else:
                    report.warnings.append(message)

        report.success = len(report.errors) == 0

        if report.success and pending_redirect_history is not None:
            # Only recorded once the build actually succeeded — an
            # aborted build's "current" URLs are incomplete (some pages
            # may never have rendered), and persisting it would plant
            # wrong redirect targets for the next, successful build.
            save_url_history(redirect_history_path, pending_redirect_history)

        if staging_root is not None and report.success:
            _replace_directory(staging_root, final_output_root)
            staging_root = None

        return report


    except ContentLoadError as exc:
        report.errors.append(str(exc))
        report.success = False
        return report

    except PandocUnavailableError as exc:
        report.errors.append(str(exc))
        report.success = False
        return report

    except ValueError as exc:
        report.errors.append(str(exc))
        report.success = False
        return report

    except Exception as exc:  # pragma: no cover - guardrail for UI/reporting

        report.errors.append(f"Erreur inattendue de build: {exc}")

        report.success = False

        return report

    finally:
        # Reached whenever the build did not end with a successful swap
        # above (an exception, or report.errors populated without raising):
        # the failed attempt must never leak into the project directory.
        if staging_root is not None:
            shutil.rmtree(staging_root, ignore_errors=True)


def _generate_pages(
    loaded: LoadedContent,
    *,
    config: ProjectConfig,
    project_root: Path,
    output_root: Path,
    tei_root: Path,
    report: BuildReport,
) -> list[GeneratedItem]:
    # The page reused verbatim as /index.html's content (see
    # _generate_home_page) must not also be indexed at its own URL —
    # that would be the same content live at two canonical addresses.
    home_source = (
        (project_root / config.home.source).resolve() if config.home.mode == "page" else None
    )

    generated: list[GeneratedItem] = []
    for item in loaded.pages:
        url = f"/{item.metadata.slug}/index.html"
        html_path = output_root / item.metadata.slug / "index.html"
        tei_path = tei_root / "pages" / f"{item.metadata.slug}.xml"
        built = _build_single_item(
            item,
            config=config,
            project_root=project_root,
            output_root=output_root,
            html_path=html_path,
            tei_path=tei_path,
            url=url,
            report=report,
            noindex=(home_source is not None and item.source_path.resolve() == home_source),
        )
        if built is not None:
            generated.append(built)
    return generated


def _generate_posts(
    loaded: LoadedContent,
    *,
    config: ProjectConfig,
    project_root: Path,
    output_root: Path,
    tei_root: Path,
    report: BuildReport,
) -> list[GeneratedItem]:
    generated: list[GeneratedItem] = []
    archive_path = config.blog.archive_path.strip("/") or "billets"

    posts = list(loaded.posts)
    if config.blog.sort_descending_by_date:
        posts.sort(key=lambda item: item.metadata.date or "", reverse=True)

    for item in posts:
        url = f"/{archive_path}/{item.metadata.slug}/index.html"
        html_path = output_root / archive_path / item.metadata.slug / "index.html"
        tei_path = tei_root / "posts" / f"{item.metadata.slug}.xml"
        built = _build_single_item(
            item,
            config=config,
            project_root=project_root,
            output_root=output_root,
            html_path=html_path,
            tei_path=tei_path,
            url=url,
            report=report,
        )
        if built is not None:
            generated.append(built)
    return generated


def _build_single_item(
    item: ContentItem,
    *,
    config: ProjectConfig,
    project_root: Path,
    output_root: Path,
    html_path: Path,
    tei_path: Path,
    url: str,
    report: BuildReport,
    noindex: bool = False,
) -> GeneratedItem | None:
    rewritten_targets: dict[str, str] = {}

    if config.content.copy_linked_assets and config.media_handling.copy_media_to_output:
        linked_copy = copy_linked_content_assets(
            references=item.linked_assets,
            project_root=project_root,
            output_root=output_root,
            html_output_dir=html_path.parent,
            source_markdown_path=item.source_path,
            item_kind=item.kind,
            item_slug=item.metadata.slug,
            assets_dir=config.paths.assets_dir,
            copy_project_assets_enabled=config.build.copy_assets,
        )

        rewritten_targets = linked_copy.rewritten_targets

        if linked_copy.copied_files:
            report.warnings.append(
                f"{item.source_path}: médias liés copiés ({len(linked_copy.copied_files)})."
            )

        if linked_copy.missing:
            for missing in linked_copy.missing:
                message = (
                    f"{item.source_path}: média lié introuvable '{missing.target}' "
                    f"({missing.resolved_path})"
                )
                if config.build.fail_on_missing_assets:
                    report.errors.append(message)
                else:
                    report.warnings.append(message)
            if config.build.fail_on_missing_assets:
                return None

    conversion = convert_markdown_file_to_tei(
        item.source_path,
        tei_path,
        google_docs_mode=(config.content.markdown_origin == "google_docs_export"),
        pandoc_command=config.build.pandoc_command,
    )
    if not conversion.success:
        report.errors.append(f"{item.source_path}: {conversion.message}")
        return None

    if rewritten_targets:
        rewrite_graphic_urls_in_tei_file(tei_path, rewritten_targets)

    report.generated_tei.append(tei_path)

    # Keep a permanent, "usable" copy of the generated TEI (full document,
    # own teiHeader — not just the fragment rendered into the page) next to
    # its Markdown source, so it can be versioned/archived alongside it.
    # Independent of the "Conserver TEI" (generate_tei_files) setting, which
    # only controls the separate build/tei staging directory.
    content_tei_path = item.source_path.with_suffix(".xml")
    shutil.copyfile(tei_path, content_tei_path)

    fragment = render_tei_file_to_html_fragment(
        tei_path,
        xslt_path=_resolve_xslt_path(config, project_root),
        parameters={
            "article_slug": item.metadata.slug,
            "clickable_figures": config.media_handling.generate_clickable_figures,
        },
    )

    lightbox_result = apply_lightbox_markup(
        fragment,
        enabled=(
            config.render.enable_lightbox
            and config.media_handling.generate_clickable_figures
        ),
        group_name=_lightbox_group_name(item, config),
        use_caption=config.media_handling.use_captions_as_fancybox_caption,
    )
    fragment = lightbox_result.html_fragment

    notes_result = apply_notes_rendering(
        fragment,
        enable_margin_notes=config.notes_rendering.enable_margin_notes,
        enable_footnotes=config.notes_rendering.enable_footnotes,
        excerpt_words=config.notes_rendering.margin_excerpt_words,
        excerpt_chars=config.notes_rendering.margin_excerpt_chars,
        prefer_words=config.notes_rendering.prefer_words_over_chars,
    )
    fragment = notes_result.html_fragment

    if lightbox_result.enhanced_images:
        report.warnings.append(
            f"{item.source_path}: images lightbox activées ({lightbox_result.enhanced_images})."
        )
    if notes_result.footnotes_count:
        report.warnings.append(
            f"{item.source_path}: notes rendues ({notes_result.footnotes_count}), "
            f"marges ({notes_result.margin_notes_count})."
        )

    article_date = (item.metadata.date or "").strip() or None
    if item.kind != "post":
        article_date = None

    lastmod = _source_lastmod(item.source_path) or item.metadata.date

    template_name = config.render.post_template if item.kind == "post" else config.render.html_template
    custom_template = load_custom_template(project_root, config, template_name)

    html_document = render_page_document(
        config=config,
        title=item.metadata.title,
        content_html=fragment,
        current_path=url,
        asset_prefix=_relative_path(html_path.parent, output_root),
        article_date=article_date,
        suppress_fragment_meta=(item.kind == "post"),
        show_title_heading=True,
        description=item.metadata.description,
        custom_template=custom_template,
        noindex=noindex,
        author=item.metadata.author,
        modified_date=lastmod if article_date else None,
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_document, encoding="utf-8")
    report.generated_html.append(html_path)

    return GeneratedItem(
        source=item.source_path,
        title=item.metadata.title,
        slug=item.metadata.slug,
        url=url,
        html_path=html_path,
        tei_path=tei_path,
        date=item.metadata.date,
        content_html=fragment,
        description=item.metadata.description,
        noindex=noindex,
        lastmod=lastmod,
    )


def _generate_home_page(
    pages: list[GeneratedItem],
    posts: list[GeneratedItem],
    *,
    config: ProjectConfig,
    project_root: Path,
    output_root: Path,
    report: BuildReport,
) -> None:
    description: str | None = None
    show_title_heading = False

    if config.home.mode == "recent_posts":
        title = config.site.title
        count = max(config.home.recent_posts_count, 0)
        recent_items = [
            (item.title, item.url, item.date, item.content_html) for item in posts[:count]
        ]
        content = render_recent_posts_fragment(
            recent_items,
            current_path="/index.html",
        )
    else:
        home_source = (project_root / config.home.source).resolve()
        page = next((item for item in pages if item.source.resolve() == home_source), None)

        if page is not None:
            content = page.content_html
            title = page.title
            # page.content_html is the raw fragment from before the
            # per-page render injected its own <h1>/description (see
            # _build_single_item) — redo both here so /index.html isn't
            # left with neither (previously: the source page at its own
            # URL got them, the home page reusing its content did not).
            description = page.description
            show_title_heading = True
        else:
            title = config.site.title
            content = "<article><h1>Accueil</h1><p>Page d'accueil non trouvée.</p></article>"
            report.warnings.append(f"Source home introuvable: {home_source}")

    index_path = output_root / "index.html"
    custom_template = load_custom_template(project_root, config, config.render.home_template)
    html = render_page_document(
        config=config,
        title=title,
        content_html=content,
        current_path="/index.html",
        asset_prefix=_relative_path(index_path.parent, output_root),
        custom_template=custom_template,
        description=description,
        show_title_heading=show_title_heading,
    )
    index_path.write_text(html, encoding="utf-8")
    report.generated_html.append(index_path)


def _archive_page_url(archive_path: str, page_number: int) -> str:
    if page_number <= 1:
        return f"/{archive_path}/index.html"
    return f"/{archive_path}/page/{page_number}/index.html"


def _paginate_posts(posts: list[GeneratedItem], per_page: int) -> list[list[GeneratedItem]]:
    if not posts:
        return [[]]
    if per_page <= 0:
        return [posts]
    return [posts[i : i + per_page] for i in range(0, len(posts), per_page)]


def _generate_archive_page(
    posts: list[GeneratedItem],
    *,
    config: ProjectConfig,
    project_root: Path,
    output_root: Path,
    report: BuildReport,
) -> list[tuple[str, str | None]]:
    """Renders the paginated archive ("Billets par page" in the Blog tab —
    previously displayed but never actually applied: the archive always
    listed every post on a single page regardless of this setting).

    Returns each generated page's (url, lastmod) for the sitemap.
    """
    if not config.blog.enabled or not config.blog.generate_archive_page:
        return []

    archive_path = config.blog.archive_path.strip("/") or "billets"
    pages = _paginate_posts(posts, config.blog.posts_per_page)
    total_pages = len(pages)
    latest_date = posts[0].lastmod if posts else None
    custom_template = load_custom_template(project_root, config, config.render.html_template)

    sitemap_entries: list[tuple[str, str | None]] = []
    for page_number, page_posts in enumerate(pages, start=1):
        current_path = _archive_page_url(archive_path, page_number)
        archive_links = [(item.title, item.url, item.date) for item in page_posts]
        title = config.blog.archive_title if page_number == 1 else f"{config.blog.archive_title} (page {page_number})"
        archive_fragment = render_archive_fragment(
            title,
            archive_links,
            current_path=current_path,
            page_number=page_number,
            total_pages=total_pages,
            prev_url=_archive_page_url(archive_path, page_number - 1) if page_number > 1 else None,
            next_url=_archive_page_url(archive_path, page_number + 1) if page_number < total_pages else None,
        )

        archive_file = output_root / current_path.lstrip("/")
        html = render_page_document(
            config=config,
            title=title,
            content_html=archive_fragment,
            current_path=current_path,
            asset_prefix=_relative_path(archive_file.parent, output_root),
            custom_template=custom_template,
        )

        archive_file.parent.mkdir(parents=True, exist_ok=True)
        archive_file.write_text(html, encoding="utf-8")
        report.generated_html.append(archive_file)
        sitemap_entries.append((current_path, latest_date))

    return sitemap_entries


def _generate_feed_and_sitemap(
    pages: list[GeneratedItem],
    posts: list[GeneratedItem],
    archive_sitemap_entries: list[tuple[str, str | None]],
    *,
    config: ProjectConfig,
    output_root: Path,
    report: BuildReport,
) -> None:
    base_url = (config.site.base_url or "").strip()
    want_feed = config.blog.enabled and config.blog.generate_rss_feed
    want_sitemap = config.build.generate_sitemap
    want_robots = config.build.generate_robots_txt

    if want_robots:
        robots_txt = render_robots_txt(base_url=base_url, include_sitemap=want_sitemap and bool(base_url))
        robots_path = output_root / "robots.txt"
        robots_path.write_text(robots_txt, encoding="utf-8")
        report.generated_html.append(robots_path)

    if not base_url:
        if want_feed:
            report.warnings.append("Flux RSS non généré: site.base_url manquant.")
        if want_sitemap:
            report.warnings.append("Sitemap non généré: site.base_url manquant.")
        return

    if want_feed:
        feed_items = [
            FeedItem(title=post.title, url=post.url, date=post.date, description=post.description)
            for post in posts
        ]
        feed_xml = render_rss_feed(
            site_title=config.site.title,
            site_description=config.site.description,
            base_url=base_url,
            language=config.site.language,
            items=feed_items,
        )
        feed_path = output_root / "feed.xml"
        feed_path.write_text(feed_xml, encoding="utf-8")
        report.generated_html.append(feed_path)

    if want_sitemap:
        urls: list[tuple[str, str | None]] = []
        home_lastmod = posts[0].lastmod if posts else None
        urls.append(("/index.html", home_lastmod))
        urls.extend(archive_sitemap_entries)
        urls.extend((item.url, item.lastmod) for item in pages if not item.noindex)
        urls.extend((item.url, item.lastmod) for item in posts)

        sitemap_xml = render_sitemap(base_url=base_url, urls=urls)
        sitemap_path = output_root / "sitemap.xml"
        sitemap_path.write_text(sitemap_xml, encoding="utf-8")
        report.generated_html.append(sitemap_path)


def _generate_search_index(
    pages: list[GeneratedItem],
    posts: list[GeneratedItem],
    *,
    config: ProjectConfig,
    output_root: Path,
    report: BuildReport,
) -> None:
    if not config.search.enabled:
        return

    excerpt_length = max(config.search.excerpt_length, 0)
    entries: list[SearchEntry] = []
    for item in [*pages, *posts]:
        text = extract_plain_text(item.content_html)
        entries.append(
            SearchEntry(
                title=item.title,
                url=item.url,
                excerpt=text[:excerpt_length],
                text=text,
            )
        )

    index_json = render_search_index(entries)
    index_path = output_root / "search-index.json"
    index_path.write_text(index_json, encoding="utf-8")
    report.generated_html.append(index_path)
    report.warnings.append(f"Index de recherche généré ({len(entries)} pages).")


def _source_history_key(source_path: Path, project_root: Path) -> str:
    resolved = source_path.resolve()
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _generate_redirects(
    pages: list[GeneratedItem],
    posts: list[GeneratedItem],
    *,
    config: ProjectConfig,
    project_root: Path,
    output_root: Path,
    report: BuildReport,
) -> dict[str, list[str]] | None:
    """Writes a meta-refresh stub at every URL a still-existing page/post
    used to have (see build/redirects.py). Returns the updated history
    to persist — the caller only actually writes it to disk once the
    whole build has succeeded.
    """
    if not config.build.generate_redirects:
        return None

    history_path = project_root / ".merope-redirects.json"
    history = load_url_history(history_path)

    current = {
        _source_history_key(item.source, project_root): item.url for item in (*pages, *posts)
    }
    updated_history = update_history(history, current)
    plans = plan_redirects(updated_history, current)

    for plan in plans:
        stale_file = output_root / plan.stale_url.lstrip("/")
        target_file = output_root / plan.target_url.lstrip("/")
        href = _relative_path(stale_file.parent, target_file)
        stale_file.parent.mkdir(parents=True, exist_ok=True)
        stale_file.write_text(render_redirect_html(href), encoding="utf-8")
        report.generated_html.append(stale_file)

    if plans:
        report.warnings.append(
            f"Redirections générées pour {len(plans)} ancienne(s) URL (changement de slug)."
        )

    return updated_history


def resolve_project_root(config: ProjectConfig, config_path: Path | None) -> Path:
    configured = Path(config.paths.project_root)
    if configured.is_absolute():
        return configured.resolve()

    candidates: list[Path] = []
    if config_path is not None:
        # A config file on disk anchors the project root: never fall through
        # to the current working directory, or a stray content/ folder left
        # over wherever the app happens to be launched from silently steals
        # every save (see the bug this guards against).
        resolved = config_path.resolve()
        candidates.append(resolved.parent)
        candidates.append(resolved.parent.parent)
    else:
        candidates.append(Path.cwd())

    for base in candidates:
        candidate = (base / configured).resolve()
        if (candidate / config.paths.content_dir).exists() or (candidate / config.paths.pages_dir).exists():
            return candidate

    # Nothing on disk yet to confirm against (a config saved before any
    # content directory was created): default to the scaffold's own layout,
    # config_path.parent.parent (project_root/config/site.json), falling
    # back to config_path.parent when config_path is None.
    default_base = candidates[-1] if config_path is not None else candidates[0]
    return (default_base / configured).resolve()


def _resolve_xslt_path(config: ProjectConfig, project_root: Path) -> Path | None:
    name = (config.render.tei_to_html_xslt or "").strip()
    if not name:
        return None
    candidate = Path(name)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    theme_candidate = project_root / config.paths.xslt_dir / candidate.name
    if theme_candidate.exists():
        return theme_candidate
    local_candidate = project_root / candidate
    if local_candidate.exists():
        return local_candidate
    return None


def _relative_path(from_dir: Path, to_dir: Path) -> str:
    relative = os.path.relpath(to_dir, start=from_dir)
    return relative.replace("\\", "/")


def _source_lastmod(source_path: Path) -> str | None:
    """The source .md file's own filesystem mtime, as an ISO date — a
    more accurate sitemap <lastmod> than the publication date alone
    (which never changes even when a post/page is later edited, and
    doesn't exist at all for a page, only a post)."""
    try:
        mtime = source_path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, tz=timezone.utc).date().isoformat()


def _lightbox_group_name(item: ContentItem, config: ProjectConfig) -> str:
    if config.media_handling.fancybox_group_posts:
        return f"{item.kind}-{item.metadata.slug}"
    return "site"


def _guard_banner_asset(config: ProjectConfig, *, project_root: Path, report: BuildReport) -> None:
    if not config.banner.enabled:
        return

    image = (config.banner.image or "").strip()
    if not image:
        config.banner.enabled = False
        report.warnings.append("Bannière désactivée: chemin d'image vide.")
        return

    if _URI_SCHEME_RE.match(image) or image.startswith("//"):
        return

    candidate = Path(image)
    if not candidate.is_absolute():
        candidate = (project_root / image.lstrip("/\\")).resolve()

    if candidate.exists():
        return

    config.banner.enabled = False
    report.warnings.append(f"Bannière désactivée: image introuvable ({candidate}).")


_EXTERNAL_LINKS_PATH = "liens-externes"


def _generate_external_link_pages(
    config: ProjectConfig, *, project_root: Path, output_root: Path, report: BuildReport
) -> None:
    """"Lien externe" menu entries open in an iframe wrapped in the site's own
    banner/menus/footer, instead of navigating away or opening a new tab.

    Generates one wrapper page per external ``MenuLink`` (top menu, side menu
    children, and side menu section headers themselves — a section can now be
    a clickable link with or without children) and rewrites that link's
    ``target`` in ``config`` (the build's runtime copy only — never the
    on-disk config) to point at the generated page. Runs before any other
    page is rendered, since every page includes the top/side menus built from
    these same links.
    """
    external_links: list[MenuLink | SideMenuSection | SideMenuSubSection] = [
        item for item in config.menus.top if item.target_type == "external"
    ]
    for section in config.menus.side:
        if section.target_type == "external":
            external_links.append(section)
        external_links.extend(child for child in section.children if child.target_type == "external")
        for subsection in section.subsections:
            if subsection.target_type == "external":
                external_links.append(subsection)
            external_links.extend(child for child in subsection.children if child.target_type == "external")
    external_links = [item for item in external_links if (item.target or "").strip()]
    if not external_links:
        return

    used_slugs: set[str] = set()
    custom_template = load_custom_template(project_root, config, config.render.html_template)

    for item in external_links:
        original_url = item.target.strip()
        slug = ensure_unique_slug(slugify(item.label, mode=config.content.slugify_mode), used_slugs)
        wrapper_path = f"/{_EXTERNAL_LINKS_PATH}/{slug}/index.html"
        wrapper_file = output_root / _EXTERNAL_LINKS_PATH / slug / "index.html"

        content_html = render_external_link_fragment(label=item.label, url=original_url)
        html = render_page_document(
            config=config,
            title=item.label,
            content_html=content_html,
            current_path=wrapper_path,
            asset_prefix=_relative_path(wrapper_file.parent, output_root),
            custom_template=custom_template,
        )
        wrapper_file.parent.mkdir(parents=True, exist_ok=True)
        wrapper_file.write_text(html, encoding="utf-8")
        report.generated_html.append(wrapper_file)

        item.target = wrapper_path

    report.warnings.append(f"Liens externes intégrés en iframe: {len(external_links)}.")
