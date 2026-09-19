"""Lossless round-trip of JSON data this version of MEROPE doesn't
recognize, and atomic writing of site.json.

See bloggen.config.models.ProjectConfig.unknown_data's docstring for the
mechanism: every section dataclass carries a passthrough bag for keys it
doesn't know about, populated on ProjectConfig.from_dict and merged back
in ProjectConfig.to_dict, with known fields always taking priority.
"""

from __future__ import annotations

import json

import pytest

import bloggen.content.atomic_write as atomic_write_module
from bloggen.config.defaults import build_default_config
from bloggen.config.io import ConfigValidationError, load_config, parse_config, save_config, serialize_config
from bloggen.config.models import MenuLink, SiteConfig, _section_to_dict
from bloggen.ui.menu_editor import move_top_menu_item_up, remove_top_menu_item, toggle_top_menu_item


def _base_raw() -> dict:
    return json.loads(serialize_config(build_default_config()))


# -- pure round-trip: root/section/nested ------------------------------------


def test_unknown_root_key_survives_load_and_save(tmp_path):
    raw = _base_raw()
    raw["future_extension"] = {"enabled": True, "payload": [1, 2, 3]}
    path = tmp_path / "site.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(path)
    save_config(config, path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["future_extension"] == {"enabled": True, "payload": [1, 2, 3]}


def test_unknown_key_in_a_known_section_survives_load_and_save(tmp_path):
    raw = _base_raw()
    raw["content"]["future_option"] = {"mode": "experimental"}
    path = tmp_path / "site.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(path)
    save_config(config, path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["content"]["future_option"] == {"mode": "experimental"}


def test_unknown_nested_json_values_keep_their_original_types(tmp_path):
    raw = _base_raw()
    raw["nested_probe"] = {
        "null": None,
        "true": True,
        "false": False,
        "int": 123,
        "float": 12.5,
        "text": "texte",
        "list": [1, 2, {"x": None}],
        "nested": {"items": ["a", "b"]},
    }
    path = tmp_path / "site.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(path)
    save_config(config, path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["nested_probe"] == raw["nested_probe"]


def test_editing_a_known_field_does_not_disturb_the_opaque_sibling(tmp_path):
    raw = _base_raw()
    raw["site"]["future_option"] = {"x": 1}
    path = tmp_path / "site.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(path)
    config.site.title = "Nouveau titre"
    save_config(config, path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["site"]["title"] == "Nouveau titre"
    assert saved["site"]["future_option"] == {"x": 1}


def test_a_key_that_becomes_a_real_field_is_read_and_written_as_that_field():
    """connu > opaque: if _extra_fields somehow still held a name that is
    also a declared field, the known field's current value must win in
    the output, never a stale opaque copy."""
    site = SiteConfig(title="Valeur reelle", unknown_data={"title": "valeur fantome"})
    assert _section_to_dict(site)["title"] == "Valeur reelle"


def test_opaque_data_does_not_let_an_invalid_known_field_bypass_validation(tmp_path):
    """The lossless mechanism must never weaken validation of known
    fields: an invalid site.title alongside an opaque sibling key is
    still rejected exactly as it would be without that sibling."""
    raw = _base_raw()
    raw["site"]["future_option"] = {"x": 1}
    raw["site"]["title"] = ""

    config = parse_config(raw, validate=False)
    with pytest.raises(ConfigValidationError, match="site.title"):
        save_config(config, tmp_path / "site.json")


# -- menus: top / side / subsections / children -------------------------------


def test_unknown_key_in_a_top_menu_link_survives_round_trip(tmp_path):
    raw = _base_raw()
    raw["menus"]["top"][0]["future_menu_flag"] = "keep-me"
    path = tmp_path / "site.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(path)
    save_config(config, path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["menus"]["top"][0]["future_menu_flag"] == "keep-me"


def test_unknown_key_in_a_side_subsection_child_survives_round_trip(tmp_path):
    raw = _base_raw()
    raw["menus"]["side"] = [
        {
            "label": "Section",
            "children": [],
            "subsections": [
                {
                    "label": "Sous-section",
                    "children": [
                        {
                            "label": "Billet",
                            "target": "/billets/a.html",
                            "target_type": "internal",
                            "enabled": True,
                            "new_tab": False,
                            "future_child_flag": "keep-me-too",
                        }
                    ],
                }
            ],
        }
    ]
    path = tmp_path / "site.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(path)
    save_config(config, path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    child = saved["menus"]["side"][0]["subsections"][0]["children"][0]
    assert child["future_child_flag"] == "keep-me-too"


def test_reordering_top_menu_items_keeps_opaque_data_with_the_right_item():
    top = [
        MenuLink("A", "/a", unknown_data={"tag": "A"}),
        MenuLink("B", "/b", unknown_data={"tag": "B"}),
        MenuLink("C", "/c", unknown_data={"tag": "C"}),
    ]
    config = build_default_config()
    config.menus.top = top

    move_top_menu_item_up(config.menus.top, 2)  # swap B and C
    labels_and_tags = [(item.label, item.unknown_data["tag"]) for item in config.menus.top]

    assert labels_and_tags == [("A", "A"), ("C", "C"), ("B", "B")]


def test_deleting_a_top_menu_item_does_not_leak_its_opaque_data_onto_a_sibling():
    top = [
        MenuLink("A", "/a", unknown_data={"tag": "A"}),
        MenuLink("B", "/b", unknown_data={"tag": "B"}),
    ]
    remove_top_menu_item(top, 0)

    assert [(item.label, item.unknown_data) for item in top] == [("B", {"tag": "B"})]


def test_toggling_a_top_menu_item_keeps_its_own_opaque_data():
    top = [MenuLink("A", "/a", unknown_data={"tag": "A"})]
    toggle_top_menu_item(top, 0)

    assert top[0].enabled is False
    assert top[0].unknown_data == {"tag": "A"}


# SideSectionDialog/SideSubSectionDialog/MenuLinkDialog "Modifier" edits
# (apply()) are covered in tests/test_menu_link_dialog.py, alongside their
# existing dialog test infrastructure. The real MainWindow load -> edit ->
# save cycle (new config, successive opens, Save As) is covered in
# tests/test_main_window_inactive_options.py, reusing its existing
# module-scoped MainWindow fixture instead of creating another one here —
# see that file's "lossless" section.


# -- FTP password: never restored in plaintext ---------------------------------


def test_ftp_password_is_never_captured_as_opaque_passthrough_data(tmp_path, monkeypatch):
    """The lossless mechanism must never treat ftp.password as opaque
    data to preserve: it's a declared field, exclusively governed by
    bloggen.config.io's keyring handling, which always strips it from
    disk regardless of credential-store availability."""
    import bloggen.publish.ftp_credentials as ftp_credentials

    monkeypatch.setattr(ftp_credentials, "save_password", lambda *args: False)
    monkeypatch.setattr(ftp_credentials, "load_password", lambda *args: "")

    raw = _base_raw()
    raw["ftp"] = {
        "host": "ftp.example.org",
        "username": "user",
        "password": "secret-en-clair",
    }
    path = tmp_path / "site.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(path)
    assert config.ftp.unknown_data == {}

    save_config(config, path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["ftp"]["password"] == ""
    assert "secret-en-clair" not in path.read_text(encoding="utf-8")


# -- Atomic write ----------------------------------------------------------


def test_save_config_writes_through_the_shared_atomic_write_helper(tmp_path, monkeypatch):
    path = tmp_path / "site.json"
    calls: list[str] = []
    real_atomic_write_text = atomic_write_module.atomic_write_text

    def spy(*args, **kwargs):
        calls.append("atomic_write_text")
        return real_atomic_write_text(*args, **kwargs)

    monkeypatch.setattr("bloggen.config.io.atomic_write_text", spy)

    save_config(build_default_config(), path)

    assert calls == ["atomic_write_text"]
    assert path.is_file()


def test_save_config_failure_before_replace_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    path = tmp_path / "site.json"
    original_config = build_default_config()
    original_config.site.title = "Titre original"
    save_config(original_config, path)
    original_bytes = path.read_bytes()

    def fail_replace(_source, _target):
        raise OSError("simulated I/O failure before replace")

    monkeypatch.setattr(atomic_write_module.os, "replace", fail_replace)

    new_config = build_default_config()
    new_config.site.title = "Titre qui ne doit jamais atteindre le disque"

    with pytest.raises(OSError, match="simulated I/O failure"):
        save_config(new_config, path)

    assert path.read_bytes() == original_bytes
    assert json.loads(path.read_text(encoding="utf-8"))["site"]["title"] == "Titre original"
    # No stray temporary file left behind either (atomic_write_text's own
    # cleanup, exercised end-to-end through save_config here).
    assert list(path.parent.glob(f".{path.name}.tmp-*")) == []
