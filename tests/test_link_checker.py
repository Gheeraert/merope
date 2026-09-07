"""bloggen.build.link_checker: a post-build sweep of every internal
<a href>/<img src> in the generated site, confirming each one actually
resolves to a real file — the audit's "aucun contrôle de doublons ou
d'URL réellement produites", e.g. a menu left pointing at a slug that
was since renamed.
"""

from __future__ import annotations

from pathlib import Path
import uuid

from bloggen.build.link_checker import (
    check_broken_links,
    check_canonical_links,
    check_structured_data,
    find_orphan_pages,
)

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


# -- orphan pages -------------------------------------------------------


def test_a_page_with_no_incoming_link_is_reported_as_orphan():
    site = _site("orphan")
    (site / "billets" / "isole").mkdir(parents=True)
    (site / "index.html").write_text("<html><body>Accueil, sans lien vers le billet.</body></html>", encoding="utf-8")
    (site / "billets" / "isole" / "index.html").write_text("<html><body>Billet isolé.</body></html>", encoding="utf-8")

    orphans = find_orphan_pages(site)
    assert orphans == [site / "billets" / "isole" / "index.html"]


def test_a_page_linked_from_anywhere_is_not_orphan():
    site = _site("not_orphan")
    (site / "billets" / "lie").mkdir(parents=True)
    (site / "index.html").write_text(
        '<html><body><a href="billets/lie/index.html">Un billet</a></body></html>', encoding="utf-8"
    )
    (site / "billets" / "lie" / "index.html").write_text("<html><body>Contenu.</body></html>", encoding="utf-8")

    assert find_orphan_pages(site) == []


def test_the_home_page_itself_is_never_considered_orphan():
    site = _site("home_exempt")
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text("<html><body>Accueil.</body></html>", encoding="utf-8")

    assert find_orphan_pages(site) == []


def test_a_noindexed_page_is_never_considered_orphan():
    """The home.source page duplicated onto /index.html when
    home.mode == "page" is deliberately never linked to at its own URL
    (its canonical points at /index.html instead, and it's marked
    noindex) — that's by design, not a stray page to flag."""
    site = _site("noindex_exempt")
    (site / "accueil").mkdir(parents=True)
    (site / "index.html").write_text("<html><body>Accueil (dupliqué ici).</body></html>", encoding="utf-8")
    (site / "accueil" / "index.html").write_text(
        '<html><head><meta name="robots" content="noindex,follow"></head>'
        "<body>Accueil (page source, jamais liée directement).</body></html>",
        encoding="utf-8",
    )

    assert find_orphan_pages(site) == []


# -- canonical links ------------------------------------------------------


def test_canonical_link_matching_base_url_and_an_existing_page_is_fine():
    site = _site("canonical_ok")
    (site / "billets" / "un-billet").mkdir(parents=True)
    (site / "billets" / "un-billet" / "index.html").write_text(
        '<html><head><link rel="canonical" href="https://exemple.fr/billets/un-billet/index.html"></head>'
        "<body></body></html>",
        encoding="utf-8",
    )

    assert check_canonical_links(site, "https://exemple.fr") == []


def test_canonical_link_pointing_at_a_missing_page_is_reported():
    site = _site("canonical_missing")
    (site / "index.html").write_text(
        '<html><head><link rel="canonical" href="https://exemple.fr/introuvable/index.html"></head>'
        "<body></body></html>",
        encoding="utf-8",
    )

    issues = check_canonical_links(site, "https://exemple.fr")
    assert len(issues) == 1
    assert "introuvable" in issues[0].reason


def test_canonical_link_with_a_mismatched_base_url_is_reported():
    site = _site("canonical_mismatch")
    (site / "index.html").write_text(
        '<html><head><link rel="canonical" href="https://autre-domaine.example/index.html"></head>'
        "<body></body></html>",
        encoding="utf-8",
    )

    issues = check_canonical_links(site, "https://exemple.fr")
    assert len(issues) == 1
    assert "base_url" in issues[0].reason


def test_canonical_check_is_skipped_entirely_without_a_configured_base_url():
    site = _site("canonical_no_base_url")
    (site / "index.html").write_text(
        '<html><head><link rel="canonical" href="https://exemple.fr/introuvable/index.html"></head>'
        "<body></body></html>",
        encoding="utf-8",
    )

    assert check_canonical_links(site, "") == []


# -- structured data (JSON-LD) --------------------------------------------


def test_valid_and_complete_json_ld_is_fine():
    site = _site("jsonld_ok")
    (site / "index.html").write_text(
        '<html><head><script type="application/ld+json">'
        '{"@context": "https://schema.org", "@type": "WebSite", '
        '"name": "Mon Site", "url": "https://exemple.fr/index.html"}'
        "</script></head><body></body></html>",
        encoding="utf-8",
    )

    assert check_structured_data(site) == []


def test_malformed_json_ld_is_reported():
    site = _site("jsonld_malformed")
    (site / "index.html").write_text(
        '<html><head><script type="application/ld+json">{ceci n\'est pas du JSON</script></head>'
        "<body></body></html>",
        encoding="utf-8",
    )

    issues = check_structured_data(site)
    assert len(issues) == 1
    assert "JSON invalide" in issues[0].reason


def test_json_ld_missing_a_required_field_for_its_type_is_reported():
    site = _site("jsonld_incomplete")
    (site / "billets" / "un-billet").mkdir(parents=True)
    (site / "billets" / "un-billet" / "index.html").write_text(
        '<html><head><script type="application/ld+json">'
        '{"@context": "https://schema.org", "@type": "BlogPosting", '
        '"url": "https://exemple.fr/billets/un-billet/index.html"}'
        "</script></head><body></body></html>",
        encoding="utf-8",
    )

    issues = check_structured_data(site)
    assert len(issues) == 1
    assert "headline" in issues[0].reason


def test_an_unrecognized_json_ld_type_has_no_required_fields_checked():
    site = _site("jsonld_unknown_type")
    (site / "index.html").write_text(
        '<html><head><script type="application/ld+json">'
        '{"@context": "https://schema.org", "@type": "Organization"}'
        "</script></head><body></body></html>",
        encoding="utf-8",
    )

    assert check_structured_data(site) == []
