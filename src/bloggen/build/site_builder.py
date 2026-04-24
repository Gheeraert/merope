"""Static site builder for MEROPE V1."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil

from bloggen.build.assets import (
    copy_builtin_resources,
    copy_linked_content_assets,
    copy_project_assets,
)
from bloggen.build.reports import BuildReport
from bloggen.config.models import ProjectConfig
from bloggen.content.loader import ContentItem, LoadedContent, load_content
from bloggen.render.html_templates import render_archive_fragment, render_page_document
from bloggen.render.lightbox import apply_lightbox_markup
from bloggen.render.margin_notes import apply_notes_rendering
from bloggen.render.xslt_runner import render_tei_file_to_html_fragment
from bloggen.tei.pandoc_converter import PandocUnavailableError, convert_markdown_file_to_tei
from bloggen.tei.postprocess import rewrite_graphic_urls_in_tei_file

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


def build_site(config: ProjectConfig, *, config_path: Path | None = None) -> BuildReport:
    project_root = _resolve_project_root(config, config_path)
    runtime_config = copy.deepcopy(config)
    output_root = (project_root / config.paths.output_dir).resolve()
    requested_tei_root = (project_root / config.paths.tei_dir).resolve()

    report = BuildReport(success=False, output_dir=output_root, tei_dir=requested_tei_root)

    try:
        if config.build.clean_output_dir and output_root.exists():
            shutil.rmtree(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        _guard_banner_asset(runtime_config, project_root=project_root, report=report)

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
        generated_posts = _generate_posts(
            loaded,
            config=runtime_config,
            project_root=project_root,
            output_root=output_root,
            tei_root=tei_root,
            report=report,
        )

        _generate_home_page(
            generated_pages,
            generated_posts,
            config=runtime_config,
            project_root=project_root,
            output_root=output_root,
            report=report,
        )
        _generate_archive_page(
            generated_posts,
            config=runtime_config,
            output_root=output_root,
            report=report,
        )

        copied_assets = 0
        if runtime_config.build.copy_assets:
            copied_assets = copy_project_assets(project_root, runtime_config.paths.assets_dir, output_root)
        copied_resources = copy_builtin_resources(output_root)

        report.warnings.append(f"Ressources intégrées copiées: {copied_resources}.")
        if runtime_config.build.copy_assets:
            report.warnings.append(f"Assets globaux copiés: {copied_assets}.")

        if not runtime_config.render.generate_tei_files and temporary_tei_root.exists():
            shutil.rmtree(temporary_tei_root, ignore_errors=True)

        report.success = len(report.errors) == 0
        return report

    except PandocUnavailableError as exc:
        report.errors.append(str(exc))
        report.success = False
        return report
    except Exception as exc:  # pragma: no cover - guardrail for UI/reporting
        report.errors.append(f"Erreur inattendue de build: {exc}")
        report.success = False
        return report


def _generate_pages(
    loaded: LoadedContent,
    *,
    config: ProjectConfig,
    project_root: Path,
    output_root: Path,
    tei_root: Path,
    report: BuildReport,
) -> list[GeneratedItem]:
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

    html_document = render_page_document(
        config=config,
        title=item.metadata.title,
        content_html=fragment,
        current_path=url,
        asset_prefix=_relative_path(html_path.parent, output_root),
        article_date=article_date,
        suppress_fragment_meta=(item.kind == "post"),
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
    if not config.home.enabled:
        return

    home_source = (project_root / config.home.source).resolve()
    page = next((item for item in pages if item.source.resolve() == home_source), None)

    if page is not None:
        content = page.content_html
        title = page.title
    else:
        title = config.site.title
        content = "<article><h1>Accueil</h1><p>Page d'accueil non trouvée.</p></article>"
        report.warnings.append(f"Source home introuvable: {home_source}")

    if config.home.show_recent_posts and posts:
        recent_count = max(config.home.recent_posts_count, 0)
        links = [(post.title, post.url, post.date) for post in posts[:recent_count]]
        recent_html = render_archive_fragment("Billets récents", links, current_path="/index.html")
        content = f"{content}\n{recent_html}"

    index_path = output_root / "index.html"
    html = render_page_document(
        config=config,
        title=title,
        content_html=content,
        current_path="/index.html",
        asset_prefix=_relative_path(index_path.parent, output_root),
    )
    index_path.write_text(html, encoding="utf-8")
    report.generated_html.append(index_path)


def _generate_archive_page(
    posts: list[GeneratedItem],
    *,
    config: ProjectConfig,
    output_root: Path,
    report: BuildReport,
) -> None:
    if not config.blog.enabled or not config.blog.generate_archive_page:
        return

    archive_path = config.blog.archive_path.strip("/") or "billets"
    archive_links = [(item.title, item.url, item.date) for item in posts]
    archive_fragment = render_archive_fragment(
        config.blog.archive_title,
        archive_links,
        current_path=f"/{archive_path}/index.html",
    )

    archive_file = output_root / archive_path / "index.html"
    html = render_page_document(
        config=config,
        title=config.blog.archive_title,
        content_html=archive_fragment,
        current_path=f"/{archive_path}/index.html",
        asset_prefix=_relative_path(archive_file.parent, output_root),
    )

    archive_file.parent.mkdir(parents=True, exist_ok=True)
    archive_file.write_text(html, encoding="utf-8")
    report.generated_html.append(archive_file)


def _resolve_project_root(config: ProjectConfig, config_path: Path | None) -> Path:
    configured = Path(config.paths.project_root)
    if configured.is_absolute():
        return configured.resolve()

    candidates: list[Path] = []
    if config_path is not None:
        resolved = config_path.resolve()
        candidates.append(resolved.parent)
        candidates.append(resolved.parent.parent)
    candidates.append(Path.cwd())

    for base in candidates:
        candidate = (base / configured).resolve()
        if (candidate / config.paths.content_dir).exists() or (candidate / config.paths.pages_dir).exists():
            return candidate

    return (candidates[0] / configured).resolve()


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
