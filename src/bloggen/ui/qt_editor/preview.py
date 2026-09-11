"""One-shot Qt editor preview through Mérope's real publication pipeline.

The build helpers in this module deliberately know nothing about Qt widgets.
They consume an immutable canonical snapshot and own only temporary files.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bloggen.build.assets import copy_project_assets, copy_theme_resources
from bloggen.build.reports import BuildReport
from bloggen.build.site_builder import _build_single_item
from bloggen.config.models import ProjectConfig
from bloggen.content.assets import collect_linked_assets
from bloggen.content.loader import ContentItem
from bloggen.content.metadata import ContentMetadataError, build_content_metadata
from bloggen.content.writer import write_content_file
from bloggen.markdown.front_matter import parse_front_matter
from bloggen.markdown.normalizer import normalize_markdown_text
from bloggen.tei.pandoc_converter import PandocUnavailableError


_KINDS = frozenset({"page", "post"})
_TEMP_MARKDOWN_PREFIX = ".__merope_qt_preview__-"


class PreviewBuildError(RuntimeError):
    """The one-shot preview could not be built or displayed safely."""


@dataclass(frozen=True, slots=True)
class PreviewSnapshot:
    body_markdown: str
    metadata: dict[str, str]
    current_path: Path
    current_kind: str | None = None


@dataclass(frozen=True, slots=True)
class PreviewArtifact:
    scratch_dir: Path
    html_path: Path
    pointer_path: Path


def determine_content_kind(
    snapshot: PreviewSnapshot,
    *,
    config: ProjectConfig,
    project_root: Path,
) -> str:
    """Resolve page/post from every trustworthy source and reject conflicts."""

    candidates: list[tuple[str, str]] = []
    declared = (snapshot.metadata.get("type") or "").strip().lower()
    if declared:
        if declared not in _KINDS:
            raise PreviewBuildError(f"Type de contenu invalide : {declared!r}.")
        candidates.append(("métadonnées", declared))

    if snapshot.current_kind is not None:
        session_kind = snapshot.current_kind.strip().lower()
        if session_kind not in _KINDS:
            raise PreviewBuildError(
                f"Type de session d’éditeur invalide : {snapshot.current_kind!r}."
            )
        candidates.append(("session", session_kind))

    resolved_path = snapshot.current_path.resolve()
    root = Path(project_root).resolve()
    page_root = (root / config.paths.pages_dir).resolve()
    post_root = (root / config.paths.posts_dir).resolve()
    if resolved_path.is_relative_to(page_root):
        candidates.append(("dossier pages", "page"))
    if resolved_path.is_relative_to(post_root):
        candidates.append(("dossier billets", "post"))

    if not candidates:
        raise PreviewBuildError(
            "Impossible de déterminer si ce contenu est une page ou un billet."
        )
    kinds = {kind for _, kind in candidates}
    if len(kinds) != 1:
        details = ", ".join(f"{source}={kind}" for source, kind in candidates)
        raise PreviewBuildError(
            "Le type du contenu est contradictoire entre ses métadonnées, sa "
            f"session et son emplacement ({details})."
        )
    return candidates[0][1]


def build_preview_artifact(
    snapshot: PreviewSnapshot,
    *,
    config: ProjectConfig,
    project_root: Path,
) -> PreviewArtifact:
    """Build one isolated artifact and always remove the neighboring source."""

    source_path = Path(snapshot.current_path).resolve()
    kind = determine_content_kind(snapshot, config=config, project_root=project_root)
    temp_name = f"{_TEMP_MARKDOWN_PREFIX}{uuid.uuid4().hex}.md"
    temp_path = source_path.parent / temp_name
    scratch: Path | None = None
    try:
        write_content_file(
            source_path.parent,
            temp_name,
            dict(snapshot.metadata),
            snapshot.body_markdown,
        )
        raw_markdown = temp_path.read_text(encoding="utf-8")
        parsed = parse_front_matter(raw_markdown)
        normalized = normalize_markdown_text(
            parsed.body,
            google_docs_mode=(
                config.content.markdown_origin == "google_docs_export"
            ),
        )
        item_metadata = build_content_metadata(
            front_matter=parsed.metadata,
            kind=kind,
            default_layout=(
                config.content.default_page_layout
                if kind == "page"
                else config.content.default_post_layout
            ),
            source_path=str(temp_path),
        )
        linked_assets = collect_linked_assets(
            temp_path,
            normalized,
            project_root=project_root,
        )
        item = ContentItem(
            source_path=temp_path,
            kind=kind,
            metadata=item_metadata,
            front_matter=parsed.metadata,
            raw_markdown=raw_markdown,
            normalized_markdown=normalized,
            linked_assets=linked_assets,
        )

        scratch = Path(tempfile.mkdtemp(prefix="merope-qt-preview-"))
        copy_theme_resources(project_root, config.paths.theme_dir, scratch)
        if config.build.copy_assets:
            copy_project_assets(project_root, config.paths.assets_dir, scratch)

        if kind == "page":
            url = f"/{item_metadata.slug}/index.html"
            item_dir = scratch / item_metadata.slug
        else:
            archive_path = config.blog.archive_path.strip("/") or "billets"
            url = f"/{archive_path}/{item_metadata.slug}/index.html"
            item_dir = scratch / archive_path / item_metadata.slug
        html_path = item_dir / "index.html"
        tei_path = scratch / "tei" / f"{item_metadata.slug}.xml"
        report = BuildReport(
            success=True,
            output_dir=scratch,
            tei_dir=scratch / "tei",
        )
        built = _build_single_item(
            item,
            config=config,
            project_root=project_root,
            output_root=scratch,
            html_path=html_path,
            tei_path=tei_path,
            url=url,
            report=report,
        )
        if built is None or report.errors:
            raise PreviewBuildError(
                "\n".join(report.errors) or "Échec de la génération de l’aperçu."
            )

        pointer_path = item_dir / "_current.txt"
        pointer_path.write_text(str(html_path.resolve()), encoding="utf-8")
        return PreviewArtifact(
            scratch_dir=scratch,
            html_path=html_path,
            pointer_path=pointer_path,
        )
    except PreviewBuildError:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        raise
    except (
        ContentMetadataError,
        PandocUnavailableError,
        OSError,
        ValueError,
    ) as exc:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        raise PreviewBuildError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - pipeline failures must clean scratch
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        raise PreviewBuildError(f"Échec de la génération de l’aperçu : {exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)


def pywebview_available() -> bool:
    """Check the optional dependency without importing it into Qt."""

    return importlib.util.find_spec("webview") is not None


def launch_preview_process(
    artifact: PreviewArtifact,
    *,
    popen_factory: Callable[..., subprocess.Popen] | None = None,
) -> subprocess.Popen:
    """Start the existing pywebview host with the artifact pointer file."""

    if not pywebview_available():
        raise PreviewBuildError(
            "Aperçu HTML indisponible : pywebview n’est pas installé."
        )
    factory = popen_factory or subprocess.Popen
    try:
        return factory(
            [
                sys.executable,
                "-m",
                "bloggen.ui.preview_process",
                str(artifact.pointer_path.resolve()),
            ],
            # The Qt child reserves its own stdout for JSONL IPC.  A
            # grandchild GUI backend must never inherit and pollute that pipe.
            stdout=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise PreviewBuildError(
            f"Impossible de lancer la fenêtre d’aperçu : {exc}"
        ) from exc


def remove_preview_artifact(artifact: PreviewArtifact | None) -> None:
    if artifact is not None:
        shutil.rmtree(artifact.scratch_dir, ignore_errors=True)
