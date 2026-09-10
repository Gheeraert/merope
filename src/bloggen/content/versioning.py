"""GUI-independent content versioning and page/post conversion services."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bloggen.content.writer import default_filename, read_content_file, write_content_file


VERSIONS_DIRNAME = ".versions"
MAX_VERSIONS_PER_DOCUMENT = 20
VERSION_PURGE_PROMPT_INTERVAL = 50
_VERSION_FILENAME_RE_TEMPLATE = r"^{stem}\.v(\d+){suffix}$"


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    """Result of archiving the current on-disk state of one document."""

    archived_path: Path | None
    versions: tuple[tuple[int, Path], ...]
    should_offer_purge: bool


@dataclass(frozen=True, slots=True)
class ContentConversionResult:
    """Filesystem and document data produced by a page/post conversion."""

    path: Path
    metadata: dict[str, str]
    body: str


def list_versions(path: Path, versions_dir: Path | None = None) -> list[tuple[int, Path]]:
    """List valid numbered archives for ``path``, oldest number first."""
    path = Path(path)
    versions_dir = Path(versions_dir) if versions_dir is not None else path.parent / VERSIONS_DIRNAME
    pattern = re.compile(
        _VERSION_FILENAME_RE_TEMPLATE.format(
            stem=re.escape(path.stem),
            suffix=re.escape(path.suffix),
        )
    )
    numbered: list[tuple[int, Path]] = []
    for existing in versions_dir.glob(f"{path.stem}.v*{path.suffix}"):
        match = pattern.match(existing.name)
        if match:
            numbered.append((int(match.group(1)), existing))
    numbered.sort(key=lambda item: item[0])
    return numbered


def archive_previous_version(
    path: Path,
    *,
    prompt_interval: int = VERSION_PURGE_PROMPT_INTERVAL,
) -> ArchiveResult:
    """Archive the current file and report whether the UI should offer purge.

    No deletion is performed here.  The caller remains responsible for any
    interactive choice and may later pass :func:`versions_to_purge` to
    :func:`purge_versions` after explicit user confirmation.
    """
    path = Path(path)
    if not path.exists():
        return ArchiveResult(None, (), False)

    versions_dir = path.parent / VERSIONS_DIRNAME
    versions_dir.mkdir(exist_ok=True)
    existing_versions = list_versions(path, versions_dir)
    next_number = existing_versions[-1][0] + 1 if existing_versions else 1
    version_path = versions_dir / f"{path.stem}.v{next_number}{path.suffix}"
    version_path.write_bytes(path.read_bytes())

    existing_versions.append((next_number, version_path))
    return ArchiveResult(
        archived_path=version_path,
        versions=tuple(existing_versions),
        should_offer_purge=(len(existing_versions) % prompt_interval == 0),
    )


def versions_to_purge(
    versions: list[tuple[int, Path]] | tuple[tuple[int, Path], ...],
    *,
    keep: int = MAX_VERSIONS_PER_DOCUMENT,
) -> list[tuple[int, Path]]:
    """Return the oldest versions exceeding ``keep``, without deleting."""
    overflow = len(versions) - keep
    return list(versions[:overflow]) if overflow > 0 else []


def purge_versions(versions: list[tuple[int, Path]]) -> None:
    """Delete exactly the version files selected by the caller."""
    for _number, old_path in versions:
        old_path.unlink(missing_ok=True)


def convert_content_file(
    path: Path,
    *,
    new_kind: str,
    target_dir: Path,
    date_value: str | None = None,
    metadata: dict[str, str] | None = None,
    body: str | None = None,
) -> ContentConversionResult:
    """Convert one content file between page and post representations.

    Validation and confirmation belong to the GUI adapter.  Supplying
    ``metadata`` and ``body`` lets that adapter reuse data it already read
    before asking the user; omitting both makes this service load the file.
    """
    if new_kind not in ("page", "post"):
        raise ValueError(f"Type de contenu inconnu: {new_kind}")
    if (metadata is None) != (body is None):
        raise ValueError("metadata et body doivent être fournis ensemble.")
    if metadata is None:
        metadata, body = read_content_file(path)

    converted_metadata = dict(metadata)
    converted_metadata["type"] = new_kind
    if new_kind == "post":
        converted_metadata["date"] = (date_value or converted_metadata.get("date", "")).strip()
    else:
        converted_metadata.pop("date", None)

    filename = default_filename(
        new_kind,
        converted_metadata.get("slug", "").strip(),
        date=converted_metadata.get("date"),
    )
    written = write_content_file(target_dir, filename, converted_metadata, body or "")
    path = Path(path)
    if written != path:
        path.unlink(missing_ok=True)
    return ContentConversionResult(written, converted_metadata, body or "")
