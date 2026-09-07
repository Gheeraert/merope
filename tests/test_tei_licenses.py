"""bloggen.tei.licenses: SPDX resolution for the Creative Commons
licenses relevant to an academic site, in the same spirit as the
companion project Mini-Métopes.
"""

from __future__ import annotations

from bloggen.tei.licenses import resolve_license


def test_known_spdx_id_resolves_to_its_canonical_name_and_url():
    resolved = resolve_license(spdx_id="CC-BY-4.0", name=None, url=None)
    assert resolved.name == "CC BY 4.0"
    assert resolved.url == "https://creativecommons.org/licenses/by/4.0/"


def test_known_spdx_id_overrides_any_given_free_text_name_and_url():
    resolved = resolve_license(spdx_id="CC0-1.0", name="Autre nom", url="https://exemple.fr/autre")
    assert resolved.name == "CC0 1.0"
    assert resolved.url == "https://creativecommons.org/publicdomain/zero/1.0/"


def test_unknown_spdx_id_falls_back_to_free_text_name_and_url():
    resolved = resolve_license(spdx_id="MIT", name="Licence MIT", url="https://exemple.fr/mit")
    assert resolved.name == "Licence MIT"
    assert resolved.url == "https://exemple.fr/mit"


def test_blank_spdx_id_falls_back_to_free_text():
    resolved = resolve_license(spdx_id="", name="Tous droits réservés", url=None)
    assert resolved.name == "Tous droits réservés"
    assert resolved.url is None


def test_nothing_given_resolves_to_nothing():
    resolved = resolve_license(spdx_id=None, name=None, url=None)
    assert resolved.name is None
    assert resolved.url is None
