"""Reusable Qt editor preview through Mérope's real publication pipeline.

The build helpers in this module deliberately know nothing about Qt widgets.
They consume immutable canonical snapshots and own only temporary files.
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
from bloggen.content.atomic_write import atomic_write_text
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
    """A preview revision could not be built or displayed safely."""


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
    session: PreviewSession | None = None


@dataclass(slots=True)
class PreviewSession:
    """One stable pointer and scratch shared by successive preview builds."""

    scratch_dir: Path
    pointer_path: Path
    revision: int = 0
    current_html_path: Path | None = None


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
    """Create a session and build its first isolated preview revision."""

    scratch = Path(tempfile.mkdtemp(prefix="merope-qt-preview-"))
    session = PreviewSession(scratch, scratch / "_current.txt")
    try:
        return build_preview_revision(
            snapshot,
            session=session,
            config=config,
            project_root=project_root,
        )
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        raise


def build_preview_revision(
    snapshot: PreviewSnapshot,
    *,
    session: PreviewSession,
    config: ProjectConfig,
    project_root: Path,
) -> PreviewArtifact:
    """Build and atomically publish one revision in an existing session.

    Theme resources and project assets live inside each revision.  A failed
    rebuild can therefore be discarded without touching the HTML currently
    displayed by pywebview.
    """

    source_path = Path(snapshot.current_path).resolve()
    kind = determine_content_kind(snapshot, config=config, project_root=project_root)
    temp_name = f"{_TEMP_MARKDOWN_PREFIX}{uuid.uuid4().hex}.md"
    temp_path = source_path.parent / temp_name
    revision = session.revision + 1
    revision_name = f"revision-{revision:06d}"
    building_dir = session.scratch_dir / f".{revision_name}-building"
    revision_dir = session.scratch_dir / revision_name
    published = False
    try:
        session.scratch_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(building_dir, ignore_errors=True)
        shutil.rmtree(revision_dir, ignore_errors=True)
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

        building_dir.mkdir(parents=True)
        copy_theme_resources(project_root, config.paths.theme_dir, building_dir)
        if config.build.copy_assets:
            copy_project_assets(project_root, config.paths.assets_dir, building_dir)

        if kind == "page":
            url = f"/{item_metadata.slug}/index.html"
            relative_item_dir = Path(item_metadata.slug)
        else:
            archive_path = config.blog.archive_path.strip("/") or "billets"
            url = f"/{archive_path}/{item_metadata.slug}/index.html"
            relative_item_dir = Path(archive_path) / item_metadata.slug
        item_dir = building_dir / relative_item_dir
        html_path = item_dir / "index.html"
        tei_path = building_dir / "tei" / f"{item_metadata.slug}.xml"
        report = BuildReport(
            success=True,
            output_dir=building_dir,
            tei_dir=building_dir / "tei",
        )
        built = _build_single_item(
            item,
            config=config,
            project_root=project_root,
            output_root=building_dir,
            html_path=html_path,
            tei_path=tei_path,
            url=url,
            report=report,
        )
        if built is None or report.errors:
            raise PreviewBuildError(
                "\n".join(report.errors) or "Échec de la génération de l’aperçu."
            )

        building_dir.replace(revision_dir)
        final_html_path = revision_dir / relative_item_dir / "index.html"
        atomic_write_text(session.pointer_path, str(final_html_path.resolve()))
        published = True
        session.revision = revision
        session.current_html_path = final_html_path
        for old_revision in session.scratch_dir.glob("revision-*"):
            if old_revision != revision_dir:
                shutil.rmtree(old_revision, ignore_errors=True)
        return PreviewArtifact(
            scratch_dir=session.scratch_dir,
            html_path=final_html_path,
            pointer_path=session.pointer_path,
            session=session,
        )
    except PreviewBuildError:
        raise
    except (
        ContentMetadataError,
        PandocUnavailableError,
        OSError,
        ValueError,
    ) as exc:
        raise PreviewBuildError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - pipeline failures must clean scratch
        raise PreviewBuildError(f"Échec de la génération de l’aperçu : {exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)
        shutil.rmtree(building_dir, ignore_errors=True)
        if not published:
            shutil.rmtree(revision_dir, ignore_errors=True)


def preview_session_from_artifact(artifact: PreviewArtifact) -> PreviewSession:
    """Return the artifact's session, adapting legacy/test artifacts safely."""

    if artifact.session is not None:
        return artifact.session
    return PreviewSession(
        scratch_dir=artifact.scratch_dir,
        pointer_path=artifact.pointer_path,
        revision=1,
        current_html_path=artifact.html_path,
    )


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
            # The Qt child's stdin is the IPC pipe from Tk, with a reader
            # thread permanently blocked on it.  On Windows, a grandchild
            # inheriting that synchronous pipe hangs in Python's startup
            # (stdio fstat serialises behind the pending ReadFile) and never
            # reaches READY.  It must get its own, unrelated stdin.
            stdin=subprocess.DEVNULL,
            # The Qt child reserves its own stdout for JSONL IPC.  A
            # grandchild GUI backend must never inherit and pollute that pipe;
            # its private pipes carry only the startup handshake/diagnostic.
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise PreviewBuildError(
            f"Impossible de lancer la fenêtre d’aperçu : {exc}"
        ) from exc


def remove_preview_artifact(artifact: PreviewArtifact | None) -> None:
    if artifact is not None:
        shutil.rmtree(artifact.scratch_dir, ignore_errors=True)
