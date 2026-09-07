"""Content metadata extraction helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from bloggen.content.slugify import is_valid_slug_format

# Accepts a bare "0000-0000-0000-000X" as well as the full ORCID URI —
# https://orcid.org/0000-0000-0000-000X — since that's what most authors
# actually copy-paste from their ORCID profile page.
_ORCID_RE = re.compile(r"(?:https?://orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])")


@dataclass(slots=True)
class ContentMetadata:
    title: str
    slug: str
    kind: str
    date: str | None
    layout: str
    author: str | None = None
    description: str | None = None
    draft: bool = False
    # Editorial last-modified date, set explicitly by the author in front
    # matter. Takes precedence over the file's filesystem mtime for the
    # sitemap <lastmod>, which is otherwise reset by any git checkout or
    # file resync unrelated to an actual content change.
    updated: str | None = None
    # Normalized "0000-0000-0000-000X" form (see normalize_orcid) — feeds
    # the TEI teiHeader's <author><idno type="ORCID">.
    orcid: str | None = None
    keywords: tuple[str, ...] = ()


class ContentMetadataError(ValueError):
    """Raised when required markdown metadata is missing or invalid."""


def build_content_metadata(
    *,
    front_matter: dict[str, str],
    kind: str,
    default_layout: str,
    source_path: str | None = None,
) -> ContentMetadata:
    context = f" dans {source_path}" if source_path else ""

    title = (front_matter.get("title") or "").strip()
    slug = (front_matter.get("slug") or "").strip()
    declared_type = (front_matter.get("type") or "").strip().lower()

    if not title:
        raise ContentMetadataError(f"Champ obligatoire manquant: title{context}.")
    if not slug:
        raise ContentMetadataError(f"Champ obligatoire manquant: slug{context}.")
    if not is_valid_slug_format(slug):
        raise ContentMetadataError(
            f"Slug invalide '{slug}'{context} : seuls les lettres minuscules, "
            "chiffres et tirets simples sont autorisés (ex. « mon-article »), "
            "sans « / », « . » ni nom réservé Windows."
        )
    if not declared_type:
        raise ContentMetadataError(f"Champ obligatoire manquant: type{context}.")
    if declared_type not in {"page", "post"}:
        raise ContentMetadataError(f"Valeur invalide pour type '{declared_type}'{context}.")
    if declared_type != kind:
        raise ContentMetadataError(
            f"Type incohérent '{declared_type}' pour un contenu attendu '{kind}'{context}."
        )

    date = (front_matter.get("date") or "").strip() or None
    if declared_type == "post" and not date:
        raise ContentMetadataError(f"Champ obligatoire manquant: date pour un post{context}.")
    if date is not None and not is_valid_iso_date(date):
        raise ContentMetadataError(f"Date invalide '{date}' (format attendu YYYY-MM-DD){context}.")

    draft = _parse_optional_bool(front_matter.get("draft"), key="draft", context=context)
    layout = (front_matter.get("layout") or default_layout).strip() or default_layout
    author = (front_matter.get("author") or "").strip() or None
    description = (front_matter.get("description") or "").strip() or None

    updated = (front_matter.get("updated") or "").strip() or None
    if updated is not None and not is_valid_iso_date(updated):
        raise ContentMetadataError(f"Date invalide '{updated}' (format attendu YYYY-MM-DD){context} pour updated.")

    raw_orcid = (front_matter.get("orcid") or "").strip() or None
    orcid = normalize_orcid(raw_orcid) if raw_orcid else None
    if raw_orcid is not None and orcid is None:
        raise ContentMetadataError(
            f"ORCID invalide '{raw_orcid}'{context} : attendu 0000-0000-0000-000X, "
            "avec une clé de contrôle correcte."
        )

    keywords = tuple(
        keyword.strip()
        for keyword in (front_matter.get("keywords") or "").split(",")
        if keyword.strip()
    )

    return ContentMetadata(
        title=title,
        slug=slug,
        kind=declared_type,
        date=date,
        layout=layout,
        author=author,
        description=description,
        draft=draft,
        updated=updated,
        orcid=orcid,
        keywords=keywords,
    )


def normalize_orcid(value: str) -> str | None:
    """Normalizes an ORCID (bare or full https://orcid.org/... URI) to
    its compact "0000-0000-0000-000X" form, verifying the ISO 7064
    mod-11-2 check digit — the same algorithm ORCID itself specifies.
    Returns None for anything that doesn't match the shape or fails the
    checksum (a typo'd digit almost always fails it), rather than
    silently accepting an ORCID-looking string that isn't a real one.
    """
    match = _ORCID_RE.fullmatch(value.strip())
    if not match:
        return None
    compact = match.group(1)
    total = 0
    for character in compact.replace("-", "")[:-1]:
        total = (total + int(character)) * 2
    remainder = (12 - total % 11) % 11
    expected = "X" if remainder == 10 else str(remainder)
    return compact if compact[-1] == expected else None


def is_valid_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _parse_optional_bool(value: str | None, *, key: str, context: str) -> bool:
    if value is None:
        return False

    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off", ""}:
        return False

    raise ContentMetadataError(f"Valeur booléenne invalide pour {key}: '{value}'{context}.")
