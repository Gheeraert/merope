"""Minimal static site builder for MEROPE V1."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from bloggen.build.assets import copy_builtin_resources, copy_project_assets
from bloggen.build.reports import BuildReport
from bloggen.config.models import ProjectConfig
from bloggen.content.loader import ContentItem, LoadedContent, load_content
from bloggen.render.html_templates import render_archive_fragment, render_page_document
from bloggen.render.xslt_runner import render_tei_file_to_html_fragment
from bloggen.tei.pandoc_converter import PandocUnavailableError, convert_markdown_file_to_tei


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
    output_root = (project_root / config.paths.output_dir).resolve()
    requested_tei_root = (project_root / config.paths.tei_dir).resolve()

    report = BuildReport(success=False, output_dir=output_root, tei_dir=requested_tei_root)

    try:
        if config.build.clean_output_dir and output_root.exists():
            shutil.rmtree(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        temporary_tei_root = output_root / "_tmp_tei_runtime"
        tei_root = requested_tei_root if config.render.generate_tei_files else temporary_tei_root
        tei_root.mkdir(parents=True, exist_ok=True)

        loaded = load_content(project_root, config)
        report.warnings.extend(loaded.warnings)

        generated_pages = _generate_pages(
            loaded,
            config=config,
            project_root=project_root,
            output_root=output_root,
            tei_root=tei_root,
            report=report,
        )
        generated_posts = _generate_posts(
            loaded,
            config=config,
            project_root=project_root,
            output_root=output_root,
            tei_root=tei_root,
            report=report,
        )

        _generate_home_page(
            generated_pages,
            generated_posts,
            config=config,
            project_root=project_root,
            output_root=output_root,
            report=report,
        )
        _generate_archive_page(generated_posts, config=config, output_root=output_root, report=report)

        if config.build.copy_assets:
            copied_assets = copy_project_assets(project_root, config.paths.assets_dir, output_root)
            copied_resources = copy_builtin_resources(output_root)
            report.warnings.append(
                f"Assets copiés: {copied_assets}, ressources intégrées: {copied_resources}."
            )

        if not config.render.generate_tei_files and temporary_tei_root.exists():
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
    html_path: Path,
    tei_path: Path,
    url: str,
    report: BuildReport,
) -> GeneratedItem | None:
    conversion = convert_markdown_file_to_tei(
        item.source_path,
        tei_path,
        google_docs_mode=(config.content.markdown_origin == "google_docs_export"),
        pandoc_command=config.build.pandoc_command,
    )
    if not conversion.success:
        report.errors.append(f"{item.source_path}: {conversion.message}")
        return None

    report.generated_tei.append(tei_path)

    fragment = render_tei_file_to_html_fragment(
        tei_path,
        xslt_path=_resolve_xslt_path(config, project_root),
    )
    html_document = render_page_document(
        config=config,
        title=item.metadata.title,
        content_html=fragment,
        current_path=url,
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
        links = [(post.title, post.url) for post in posts[:recent_count]]
        recent_html = render_archive_fragment("Billets récents", links)
        content = f"{content}\n{recent_html}"

    html = render_page_document(
        config=config,
        title=title,
        content_html=content,
        current_path="/index.html",
    )
    index_path = output_root / "index.html"
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
    archive_links = [(item.title, item.url) for item in posts]
    archive_fragment = render_archive_fragment(config.blog.archive_title, archive_links)
    html = render_page_document(
        config=config,
        title=config.blog.archive_title,
        content_html=archive_fragment,
        current_path=f"/{archive_path}/index.html",
    )

    archive_file = output_root / archive_path / "index.html"
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
