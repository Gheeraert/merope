"""Search-engine verification files (seo.verification_files, root-files/)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from bloggen.build.site_builder import build_site
from bloggen.build.verification_files import (
    VerificationFileExistsError,
    copy_root_verification_files,
    delete_local_copy,
    import_verification_file,
)
from bloggen.config.defaults import build_default_config
from bloggen.config.io import ConfigValidationError, load_config, parse_config, save_config, serialize_config
from bloggen.config.models import ProjectConfig, SeoConfig
from bloggen.tei.pandoc_converter import MarkdownToTeiResult
from bloggen.tei.validator import TeiValidationResult
from bloggen.ui.seo_panel import SeoPanel

# Deliberately not valid UTF-8 and containing a BOM and CRLF: must survive untouched.
GOOGLE_BYTES = b"\xef\xbb\xbfgoogle-site-verification: google1.html\r\n\xff\xfe\x00"

TEI = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc><titleStmt><title>T</title>'
    "</titleStmt><publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc>"
    "</fileDesc></teiHeader><text><body><div><head>T</head><p>x</p></div></body></text></TEI>"
)


def _raw() -> dict:
    return json.loads(serialize_config(build_default_config()))


# -- configuration -------------------------------------------------------------


def test_old_json_without_seo_loads_with_empty_defaults():
    raw = _raw()
    del raw["seo"]
    config = parse_config(raw)
    assert config.seo.verification_files == []


def test_verification_files_round_trip_multiple():
    config = build_default_config()
    config.seo.verification_files = ["google123456789abcdef.html", "BingSiteAuth.xml"]
    again = parse_config(json.loads(serialize_config(config)))
    assert again.seo.verification_files == ["google123456789abcdef.html", "BingSiteAuth.xml"]


def test_seo_unknown_keys_survive_round_trip(tmp_path):
    raw = _raw()
    raw["seo"] = {"verification_files": ["a.txt"], "future_key": {"x": 1}}
    path = tmp_path / "site.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    save_config(load_config(path), path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["seo"]["future_key"] == {"x": 1}
    assert saved["seo"]["verification_files"] == ["a.txt"]


def test_non_list_verification_files_falls_back_to_empty():
    raw = _raw()
    raw["seo"] = {"verification_files": "google.html"}
    assert ProjectConfig.from_dict(raw).seo.verification_files == []


@pytest.mark.parametrize(
    "bad",
    [
        "../secret.txt",
        "..\\secret.txt",
        "/subdir/file.html",
        "C:\\Windows\\file.txt",
        "/root/file.txt",
        "foo/bar.html",
        "..",
        ".",
        "",
        ".htaccess",
        "C:foo.html",
    ],
)
def test_invalid_names_rejected_by_validation(bad):
    raw = _raw()
    raw["seo"] = {"verification_files": [bad]}
    with pytest.raises(ConfigValidationError):
        parse_config(raw)


# -- import / delete (no UI) ---------------------------------------------------


def test_import_copies_bytes_into_root_files(tmp_path):
    src = tmp_path / "Downloads" / "google1.html"
    src.parent.mkdir()
    src.write_bytes(GOOGLE_BYTES)
    project = tmp_path / "proj"
    project.mkdir()
    assert import_verification_file(src, project) == "google1.html"
    assert (project / "root-files" / "google1.html").read_bytes() == GOOGLE_BYTES


def test_import_never_overwrites_silently(tmp_path):
    project = tmp_path / "proj"
    (project / "root-files").mkdir(parents=True)
    (project / "root-files" / "g.html").write_bytes(b"old")
    src = tmp_path / "g.html"
    src.write_bytes(b"new")
    with pytest.raises(VerificationFileExistsError):
        import_verification_file(src, project)
    assert (project / "root-files" / "g.html").read_bytes() == b"old"
    import_verification_file(src, project, overwrite=True)
    assert (project / "root-files" / "g.html").read_bytes() == b"new"


def test_delete_local_copy_only_touches_root_files(tmp_path):
    project = tmp_path / "proj"
    (project / "root-files").mkdir(parents=True)
    (project / "root-files" / "g.html").write_bytes(b"x")
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"keep")
    with pytest.raises(ValueError):
        delete_local_copy("../secret.txt", project)
    assert outside.exists()
    assert delete_local_copy("g.html", project) is True
    assert not (project / "root-files" / "g.html").exists()


# -- UI panel ------------------------------------------------------------------


@pytest.fixture(scope="module")
def root(tk_root):
    return tk_root


def _fail(message: str) -> None:
    pytest.fail(message)


def _panel(root, project, **kw):
    kw.setdefault("show_error", _fail)
    return SeoPanel(root, resolve_project_root=lambda: project, **kw)


def test_panel_add_copies_file_and_stores_only_the_name(root, tmp_path):
    src = tmp_path / "Downloads" / "google1.html"
    src.parent.mkdir()
    src.write_bytes(GOOGLE_BYTES)
    project = tmp_path / "proj"
    project.mkdir()
    panel = _panel(root, project, pick_file=lambda: str(src))

    panel.on_add_clicked()

    assert (project / "root-files" / "google1.html").read_bytes() == GOOGLE_BYTES
    data = panel.get_data()
    assert data.verification_files == ["google1.html"]
    assert str(tmp_path) not in json.dumps(data.verification_files)


def test_panel_same_name_asks_before_overwriting(root, tmp_path):
    project = tmp_path / "proj"
    (project / "root-files").mkdir(parents=True)
    (project / "root-files" / "g.html").write_bytes(b"old")
    src = tmp_path / "g.html"
    src.write_bytes(b"new")
    asked: list[str] = []

    def refuse(name: str) -> bool:
        asked.append(name)
        return False

    declined = _panel(root, project, confirm_overwrite=refuse)
    assert declined.add_file(src) is False
    assert asked == ["g.html"]
    assert (project / "root-files" / "g.html").read_bytes() == b"old"
    assert declined.get_data().verification_files == []

    accepted = _panel(root, project, confirm_overwrite=lambda n: True)
    assert accepted.add_file(src) is True
    assert (project / "root-files" / "g.html").read_bytes() == b"new"


def test_panel_remove_can_keep_or_delete_local_copy(root, tmp_path):
    project = tmp_path / "proj"
    (project / "root-files").mkdir(parents=True)
    for n in ("a.html", "b.xml", "c.txt"):
        (project / "root-files" / n).write_bytes(b"x")
    answers = {"a.html": True, "b.xml": False, "c.txt": None}
    panel = _panel(root, project, ask_delete_copy=lambda n: answers[n])
    panel.set_data(SeoConfig(verification_files=["a.html", "b.xml", "c.txt"]))

    assert panel.remove_file("a.html")
    assert not (project / "root-files" / "a.html").exists()
    assert panel.remove_file("b.xml")
    assert (project / "root-files" / "b.xml").exists()
    assert panel.remove_file("c.txt") is False  # cancelled: nothing changes
    assert panel.get_data().verification_files == ["c.txt"]
    assert (project / "root-files" / "c.txt").exists()


# -- build ---------------------------------------------------------------------


def _project(monkeypatch, files, *, root_files=None, **build_overrides):
    """A tiny buildable project. ``root_files`` maps name -> bytes."""
    base = Path("tests/.runtime")
    base.mkdir(parents=True, exist_ok=True)
    project = base / f"verif_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n\nTexte.\n',
        encoding="utf-8",
    )
    for name, data in (root_files or {}).items():
        (project / "root-files").mkdir(exist_ok=True)
        (project / "root-files" / name).write_bytes(data)
    (project / "config").mkdir()
    (project / "config/site.json").write_text("{}", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
    config.home.source = "content/pages/accueil.md"
    config.site.base_url = "https://example.org"
    config.seo.verification_files = list(files)
    for key, value in build_overrides.items():
        setattr(config.build, key, value)

    def fake_convert(input_path, output_path, **_kw):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)
    return project, config


def _build(project, config):
    return build_site(config, config_path=project / "config/site.json")


def test_build_copies_binary_identical_file_to_output_root(monkeypatch):
    project, config = _project(monkeypatch, ["google1.html"], root_files={"google1.html": GOOGLE_BYTES})
    report = _build(project, config)
    assert report.success, report.errors
    assert (project / "site/google1.html").read_bytes() == GOOGLE_BYTES


def test_build_restores_file_after_clean_rebuild(monkeypatch):
    project, config = _project(monkeypatch, ["google1.html"], root_files={"google1.html": GOOGLE_BYTES})
    assert config.build.clean_output_dir is True
    assert _build(project, config).success
    (project / "site/google1.html").unlink()
    (project / "site/stray.txt").write_text("stale")
    assert _build(project, config).success
    assert (project / "site/google1.html").read_bytes() == GOOGLE_BYTES
    assert not (project / "site/stray.txt").exists()


def test_build_copies_several_files(monkeypatch):
    project, config = _project(
        monkeypatch,
        ["google1.html", "BingSiteAuth.xml"],
        root_files={"google1.html": GOOGLE_BYTES, "BingSiteAuth.xml": b"<a/>"},
    )
    assert _build(project, config).success
    assert (project / "site/BingSiteAuth.xml").read_bytes() == b"<a/>"
    assert (project / "site/google1.html").read_bytes() == GOOGLE_BYTES


def test_verification_file_is_in_the_tree_ftp_publishes(monkeypatch):
    # publish_directory uploads every file under the output dir (rglob),
    # with no SEO-specific logic: being in that tree is sufficient.
    project, config = _project(monkeypatch, ["google1.html"], root_files={"google1.html": GOOGLE_BYTES})
    assert _build(project, config).success
    site = project / "site"
    published = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
    assert "google1.html" in published


def test_no_configured_file_changes_nothing(monkeypatch):
    project, config = _project(monkeypatch, [], root_files={"ignored.html": b"x"})
    report = _build(project, config)
    assert report.success
    assert not (project / "site/ignored.html").exists()  # root-files/ is never copied wholesale
    assert not any("validation" in w for w in report.warnings)


def test_missing_source_is_reported_and_follows_fail_on_missing_assets(monkeypatch):
    project, config = _project(monkeypatch, ["gone.html"])
    report = _build(project, config)
    assert report.success
    assert any("gone.html" in w and "introuvable" in w for w in report.warnings)

    project, config = _project(monkeypatch, ["gone.html"], fail_on_missing_assets=True)
    report = _build(project, config)
    assert not report.success
    assert any("gone.html" in e for e in report.errors)


@pytest.mark.parametrize(
    "bad", ["../secret.txt", "..\\secret.txt", "/etc/x.html", "C:\\Windows\\x.txt", "sub/x.html"]
)
def test_build_refuses_traversal_even_without_validation(monkeypatch, bad):
    project, config = _project(monkeypatch, [bad])
    secret = project.parent / "secret.txt"
    secret.write_bytes(b"top secret")
    report = _build(project, config)
    assert not report.success
    assert any("Fichier de validation refusé" in e for e in report.errors)
    assert not (project / "site/secret.txt").exists()


@pytest.mark.parametrize(
    "name", ["index.html", "robots.txt", "sitemap.xml", "feed.xml", "search-index.json"]
)
def test_build_refuses_collision_with_generated_files(monkeypatch, name):
    project, config = _project(monkeypatch, [name], root_files={name: b"HIJACK"})
    report = _build(project, config)
    assert not report.success
    assert any("collision" in e for e in report.errors)
    assert not (project / "site").exists()  # failed build publishes nothing


def test_collision_with_a_generated_directory(monkeypatch):
    project, config = _project(monkeypatch, ["accueil"], root_files={"accueil": b"x"})
    report = _build(project, config)
    assert not report.success
    assert any("dossier" in e for e in report.errors)


def test_collision_detected_when_robots_disabled_too(monkeypatch):
    project, config = _project(
        monkeypatch, ["robots.txt"], root_files={"robots.txt": b"x"}, generate_robots_txt=False
    )
    assert not _build(project, config).success


def test_case_only_duplicates_are_refused(tmp_path):
    (tmp_path / "root-files").mkdir()
    (tmp_path / "root-files" / "a.html").write_bytes(b"x")
    result = copy_root_verification_files(["a.html", "A.html"], tmp_path, tmp_path / "out")
    assert result.errors
    assert not (tmp_path / "out").exists()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_symlink_escaping_root_files_is_refused(tmp_path):
    (tmp_path / "root-files").mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"secret")
    try:
        os.symlink(outside, tmp_path / "root-files" / "link.txt")
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlink")
    result = copy_root_verification_files(["link.txt"], tmp_path, tmp_path / "out")
    assert result.errors
    assert not (tmp_path / "out" / "link.txt").exists()


def test_sitemap_and_robots_still_generated(monkeypatch):
    project, config = _project(monkeypatch, ["google1.html"], root_files={"google1.html": GOOGLE_BYTES})
    assert _build(project, config).success
    assert (project / "site/robots.txt").exists()
    assert (project / "site/sitemap.xml").exists()


# -- review fixes: root-files protection, unsaved project, Windows names ---------


@pytest.mark.parametrize(
    "value", ["root-files", "./root-files", "root-files/", "a/../root-files", "root-files\\sub"]
)
@pytest.mark.parametrize("clean", [True, False])
def test_output_dir_root_files_refused_and_sources_intact(monkeypatch, value, clean):
    project, config = _project(
        monkeypatch, ["g.html"], root_files={"g.html": GOOGLE_BYTES}, clean_output_dir=clean
    )
    config.paths.output_dir = value
    before = {p.name: p.read_bytes() for p in (project / "root-files").iterdir()}
    report = _build(project, config)
    assert not report.success
    assert any("root-files" in e for e in report.errors)
    assert {p.name: p.read_bytes() for p in (project / "root-files").iterdir()} == before
    assert not [p for p in project.iterdir() if ".building-" in p.name]


@pytest.mark.parametrize("value", ["root-files", "./root-files", "root-files/", "a/../root-files"])
def test_tei_dir_root_files_refused_and_sources_intact(monkeypatch, value):
    project, config = _project(monkeypatch, ["g.html"], root_files={"g.html": GOOGLE_BYTES})
    config.render.generate_tei_files = True
    config.paths.tei_dir = value
    report = _build(project, config)
    assert not report.success
    assert any("root-files" in e for e in report.errors)
    assert [p.name for p in (project / "root-files").iterdir()] == ["g.html"]
    assert (project / "root-files" / "g.html").read_bytes() == GOOGLE_BYTES


def test_tei_dir_root_files_ignored_when_tei_generation_off(monkeypatch):
    project, config = _project(monkeypatch, ["g.html"], root_files={"g.html": GOOGLE_BYTES})
    config.render.generate_tei_files = False
    config.paths.tei_dir = "root-files"
    assert _build(project, config).success
    assert (project / "root-files" / "g.html").read_bytes() == GOOGLE_BYTES


def test_tei_dir_equal_to_project_root_now_refused(monkeypatch):
    project, config = _project(monkeypatch, [], root_files={"g.html": b"x"})
    config.paths.tei_dir = "."
    assert not _build(project, config).success
    assert (project / "root-files" / "g.html").exists()


def test_panel_refuses_import_when_project_root_unknown(root, tmp_path, monkeypatch):
    src = tmp_path / "g.html"
    src.write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    errors: list[str] = []
    panel = SeoPanel(root, resolve_project_root=lambda: None, show_error=errors.append)
    assert panel.add_file(src) is False
    assert errors and "enregistrez d'abord" in errors[0]
    assert not (tmp_path / "root-files").exists()
    assert panel.get_data().verification_files == []


def test_panel_callback_exception_becomes_a_message(root, tmp_path):
    src = tmp_path / "g.html"
    src.write_bytes(b"x")
    errors: list[str] = []

    def boom() -> Path:
        raise RuntimeError("nope")

    panel = SeoPanel(root, resolve_project_root=boom, show_error=errors.append)
    assert panel.add_file(src) is False
    assert errors


def test_persistent_project_root_needs_an_anchor(tmp_path):
    from bloggen.build.site_builder import resolve_persistent_project_root

    config = build_default_config()  # project_root == "."
    assert resolve_persistent_project_root(config, None) is None
    (tmp_path / "config").mkdir()
    (tmp_path / "content").mkdir()
    assert resolve_persistent_project_root(config, tmp_path / "config" / "site.json") == tmp_path.resolve()
    config.paths.project_root = str(tmp_path)
    assert resolve_persistent_project_root(config, None) == tmp_path.resolve()


@pytest.mark.parametrize(
    "bad",
    ["CON", "con", "CON.html", "PRN.txt", "AUX.xml", "NUL", "nul.txt", "COM1", "COM9.html",
     "LPT1.txt", "LPT9", "com3.tar.gz"],
)
def test_windows_reserved_names_rejected_everywhere(bad):
    from bloggen.build.verification_files import check_verification_filename

    assert check_verification_filename(bad)
    raw = _raw()
    raw["seo"] = {"verification_files": [bad]}
    with pytest.raises(ConfigValidationError):
        parse_config(raw)


@pytest.mark.parametrize("ok", ["CONSOLE.html", "COM10.html", "COM.html", "google1.html", "LPT0.txt"])
def test_near_miss_names_stay_valid(ok):
    from bloggen.build.verification_files import check_verification_filename

    assert check_verification_filename(ok) is None
