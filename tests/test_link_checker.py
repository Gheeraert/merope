"""bloggen.build.link_checker: a post-build sweep of every internal
<a href>/<img src> in the generated site, confirming each one actually
resolves to a real file — the audit's "aucun contrôle de doublons ou
d'URL réellement produites", e.g. a menu left pointing at a slug that
was since renamed.
"""

from __future__ import annotations

from pathlib import Path
import uuid

from bloggen.build.link_checker import check_broken_links

RUNTIME_ROOT = Path("tests/.runtime")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def _site(name: str) -> Path:
    root = RUNTIME_ROOT / f"link_checker_{name}_{uuid.uuid4().hex}"
    root.mkdir(parents=True)
    return root


def test_no_broken_links_in_a_fully_consistent_site():
    site = _site("consistent")
    (site / "billets" / "un-billet").mkdir(parents=True)
    (site / "assets" / "images").mkdir(parents=True)
    (site / "index.html").write_text(
        '<html><body><a href="billets/un-billet/index.html">Un billet</a></body></html>',
        encoding="utf-8",
    )
    (site / "billets" / "un-billet" / "index.html").write_text(
        '<html><body><a href="../../index.html">Accueil</a>'
        '<img src="../../assets/images/photo.jpg"></body></html>',
        encoding="utf-8",
    )
    (site / "assets" / "images" / "photo.jpg").write_bytes(b"img")

    assert check_broken_links(site) == []


def test_detects_a_broken_internal_link():
    site = _site("broken_link")
    (site / "billets").mkdir(parents=True)
    (site / "index.html").write_text(
        # Points at a slug that doesn't exist — e.g. renamed/deleted.
        '<html><body><a href="billets/slug-renomme/index.html">Ancien lien</a></body></html>',
        encoding="utf-8",
    )

    broken = check_broken_links(site)
    assert len(broken) == 1
    assert broken[0].tag == "a"
    assert broken[0].target == "billets/slug-renomme/index.html"
    assert broken[0].source_file == site / "index.html"


def test_detects_a_broken_image():
    site = _site("broken_image")
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(
        '<html><body><img src="assets/images/manquant.jpg"></body></html>', encoding="utf-8"
    )

    broken = check_broken_links(site)
    assert len(broken) == 1
    assert broken[0].tag == "img"
    assert broken[0].attribute == "src"


def test_external_links_are_never_checked():
    site = _site("external")
    (site / "index.html").write_text(
        '<html><body>'
        '<a href="https://example.org/page">Externe</a>'
        '<a href="//cdn.example.org/lib.js">Protocole relatif</a>'
        '<a href="mailto:contact@example.org">Mail</a>'
        '<a href="tel:+33100000000">Tel</a>'
        '<a href="#section">Ancre</a>'
        '</body></html>',
        encoding="utf-8",
    )

    assert check_broken_links(site) == []


def test_links_with_a_fragment_are_resolved_on_their_path_part_only():
    site = _site("fragment")
    (site / "billets" / "un-billet").mkdir(parents=True)
    (site / "billets" / "un-billet" / "index.html").write_text("<html></html>", encoding="utf-8")
    (site / "index.html").write_text(
        '<html><body><a href="billets/un-billet/index.html#section">Lien avec ancre</a></body></html>',
        encoding="utf-8",
    )

    assert check_broken_links(site) == []


def test_empty_href_is_ignored():
    site = _site("empty_href")
    (site / "index.html").write_text(
        '<html><body><a href="">Vide</a></body></html>', encoding="utf-8"
    )
    assert check_broken_links(site) == []


def test_scans_every_html_file_recursively():
    site = _site("recursive")
    (site / "billets" / "un-billet").mkdir(parents=True)
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    (site / "billets" / "un-billet" / "index.html").write_text(
        '<html><body><img src="manquant.jpg"></body></html>', encoding="utf-8"
    )

    broken = check_broken_links(site)
    assert len(broken) == 1
    assert broken[0].source_file == site / "billets" / "un-billet" / "index.html"
