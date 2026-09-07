"""bloggen.content.metadata: front-matter parsing into ContentMetadata,
including the ORCID and keywords fields added for TEI teiHeader
enrichment (Phase 2 of the TEI Commons Publishing roadmap).
"""

from __future__ import annotations

import pytest

from bloggen.content.metadata import (
    ContentMetadataError,
    build_content_metadata,
    normalize_orcid,
)


def _front_matter(**overrides) -> dict[str, str]:
    base = {"title": "Un titre", "slug": "un-titre", "type": "page"}
    base.update(overrides)
    return base


def test_orcid_is_normalized_to_its_compact_form():
    metadata = build_content_metadata(
        front_matter=_front_matter(orcid="https://orcid.org/0000-0002-1825-0097"),
        kind="page",
        default_layout="page",
    )
    assert metadata.orcid == "0000-0002-1825-0097"


def test_orcid_already_compact_is_kept():
    metadata = build_content_metadata(
        front_matter=_front_matter(orcid="0000-0002-1825-0097"), kind="page", default_layout="page"
    )
    assert metadata.orcid == "0000-0002-1825-0097"


def test_invalid_orcid_checksum_is_rejected():
    with pytest.raises(ContentMetadataError, match="ORCID invalide"):
        build_content_metadata(
            front_matter=_front_matter(orcid="0000-0002-1825-0098"), kind="page", default_layout="page"
        )


def test_absent_orcid_is_none():
    metadata = build_content_metadata(front_matter=_front_matter(), kind="page", default_layout="page")
    assert metadata.orcid is None


def test_keywords_are_split_on_commas_and_trimmed():
    metadata = build_content_metadata(
        front_matter=_front_matter(keywords="rhétorique,  Bossuet ,XVIIe siècle"),
        kind="page",
        default_layout="page",
    )
    assert metadata.keywords == ("rhétorique", "Bossuet", "XVIIe siècle")


def test_absent_keywords_is_an_empty_tuple():
    metadata = build_content_metadata(front_matter=_front_matter(), kind="page", default_layout="page")
    assert metadata.keywords == ()


def test_blank_keyword_entries_are_dropped():
    metadata = build_content_metadata(
        front_matter=_front_matter(keywords="un, , deux,"), kind="page", default_layout="page"
    )
    assert metadata.keywords == ("un", "deux")


def test_normalize_orcid_accepts_bare_and_uri_forms():
    assert normalize_orcid("0000-0002-1825-0097") == "0000-0002-1825-0097"
    assert normalize_orcid("https://orcid.org/0000-0002-1825-0097") == "0000-0002-1825-0097"
    assert normalize_orcid("http://orcid.org/0000-0002-1825-0097") == "0000-0002-1825-0097"


def test_normalize_orcid_rejects_bad_checksum_and_garbage():
    assert normalize_orcid("0000-0002-1825-0098") is None
    assert normalize_orcid("not-an-orcid") is None
    assert normalize_orcid("") is None
