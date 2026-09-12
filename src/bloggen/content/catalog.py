"""GUI-independent discovery and validation helpers for content authoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bloggen.content.metadata import is_valid_iso_date, normalize_orcid
from bloggen.content.slugify import is_valid_slug_format
from bloggen.content.versioning import VERSIONS_DIRNAME
from bloggen.markdown.front_matter import parse_front_matter


@dataclass(frozen=True, slots=True)
class ContentCatalogEntry:
    kind: str
    title: str
    path: Path
    valid: bool = True


def scan_content_catalog(pages_dir: Path, posts_dir: Path) -> list[ContentCatalogEntry]:
    """List pages/posts recursively while retaining invalid files for repair."""

    entries: list[ContentCatalogEntry] = []
    for kind, directory in (("page", Path(pages_dir)), ("post", Path(posts_dir))):
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.md")):
            if VERSIONS_DIRNAME in path.parts:
                continue
            try:
                parsed = parse_front_matter(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                entries.append(
                    ContentCatalogEntry(kind, f"(invalide) {path.name}", path, False)
                )
                continue
            title = parsed.metadata.get("title", "").strip() or path.stem
            entries.append(ContentCatalogEntry(kind, title, path))
    return entries


def determine_content_kind(
    path: Path,
    metadata: dict[str, str],
    *,
    pages_dir: Path | None,
    posts_dir: Path | None,
) -> str | None:
    """Determine page/post from session paths and front matter without guessing."""

    location_kind: str | None = None
    resolved = Path(path).resolve()
    for kind, directory in (("page", pages_dir), ("post", posts_dir)):
        if directory is None:
            continue
        try:
            resolved.relative_to(Path(directory).resolve())
        except ValueError:
            continue
        if location_kind is not None and location_kind != kind:
            raise ValueError("Le fichier appartient simultanément aux dossiers pages et billets.")
        location_kind = kind

    declared = metadata.get("type", "").strip().lower() or None
    if declared is not None and declared not in {"page", "post"}:
        raise ValueError(f"Type de contenu invalide dans le front matter : {declared!r}.")
    if location_kind is not None and declared is not None and location_kind != declared:
        raise ValueError(
            "Le type déclaré dans le front matter contredit le dossier du contenu."
        )
    return location_kind or declared


_OPTIONAL_METADATA_FIELDS = (
    "updated",
    "author",
    "orcid",
    "keywords",
    "description",
    "layout",
)


def validate_editor_metadata(
    metadata: dict[str, str],
    kind: str,
    *,
    existing_slugs: set[str] | None = None,
    own_slug: str | None = None,
) -> dict[str, str]:
    """Validate and canonically update known authoring fields.

    Unknown front-matter keys are copied byte-for-byte at the value level.
    """

    if kind not in {"page", "post"}:
        raise ValueError("Le type doit être « page » ou « post ».")
    result = dict(metadata)
    declared = result.get("type", "").strip().lower()
    if declared and declared != kind:
        raise ValueError("Le type des métadonnées contredit le type du document.")

    title = result.get("title", "").strip()
    slug = result.get("slug", "").strip()
    if not title:
        raise ValueError("Le titre est obligatoire.")
    if not slug:
        raise ValueError("Le slug est obligatoire.")
    if not is_valid_slug_format(slug):
        raise ValueError(
            "Le slug est invalide : utilisez uniquement des lettres minuscules, "
            "des chiffres et des tirets simples."
        )
    collisions = set(existing_slugs or ())
    if own_slug:
        collisions.discard(own_slug)
    if slug in collisions:
        raise ValueError(f"Le slug « {slug} » est déjà utilisé.")

    result["title"] = title
    result["slug"] = slug
    result["type"] = kind
    if kind == "post":
        date_value = result.get("date", "").strip()
        if not is_valid_iso_date(date_value):
            raise ValueError("La date doit être au format AAAA-MM-JJ.")
        result["date"] = date_value
    else:
        result.pop("date", None)

    updated = result.get("updated", "").strip()
    if updated and not is_valid_iso_date(updated):
        raise ValueError("La date de mise à jour doit être au format AAAA-MM-JJ.")

    raw_orcid = result.get("orcid", "").strip()
    if raw_orcid:
        normalized = normalize_orcid(raw_orcid)
        if normalized is None:
            raise ValueError("L’ORCID est invalide.")
        result["orcid"] = normalized

    for key in _OPTIONAL_METADATA_FIELDS:
        value = result.get(key, "").strip()
        if value:
            result[key] = value
        else:
            result.pop(key, None)

    if result.get("draft", "").strip().lower() == "true":
        result["draft"] = "true"
    else:
        result.pop("draft", None)
    return result
