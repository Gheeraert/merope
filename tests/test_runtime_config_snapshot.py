from __future__ import annotations

import json

import pytest

from bloggen.config.models import (
    FtpConfig,
    MenuLink,
    ProjectConfig,
    SideMenuSection,
    SideMenuSubSection,
)
from bloggen.config.runtime_snapshot import (
    RuntimeSnapshotError,
    project_config_from_runtime_payload,
    project_config_to_runtime_payload,
)
from bloggen.publish import ftp_credentials


def _rich_config() -> ProjectConfig:
    config = ProjectConfig()
    config.site.title = "Configuration vivante"
    config.site.author = "Bossuet"
    config.banner.enabled = True
    config.banner.image = "assets/banner.jpg"
    config.paths.project_root = "projet"
    config.content.slugify_mode = "unicode"
    config.menus.top = [MenuLink("Accueil", "/index.html")]
    config.menus.side_title = "Sommaire"
    config.menus.side = [
        SideMenuSection(
            "Œuvres",
            children=[MenuLink("Sermons", "/sermons.html")],
            subsections=[
                SideMenuSubSection(
                    "Meaux",
                    children=[MenuLink("Discours", "/discours.html")],
                )
            ],
        )
    ]
    config.render.theme_name = "academique"
    config.media_handling.images_dir = "media/images"
    config.notes_rendering.margin_excerpt_words = 12
    config.footer.text = "Pied de page"
    config.build.pandoc_command = "pandoc-custom"
    config.search.excerpt_length = 240
    config.ftp = FtpConfig(
        host="ftp.example.org",
        username="bossuet",
        password="ULTRA_SECRET",
    )
    return config


def test_runtime_snapshot_round_trip_preserves_renderer_configuration():
    original = _rich_config()

    payload = project_config_to_runtime_payload(original)
    restored = project_config_from_runtime_payload(payload)

    original_dict = original.to_dict()
    restored_dict = restored.to_dict()
    for section in (
        "site",
        "banner",
        "paths",
        "content",
        "home",
        "blog",
        "menus",
        "render",
        "media_handling",
        "notes_rendering",
        "footer",
        "build",
        "search",
    ):
        assert restored_dict[section] == original_dict[section]
    assert restored.ftp == FtpConfig()


def test_runtime_snapshot_never_contains_ftp_or_password():
    payload = project_config_to_runtime_payload(_rich_config())
    encoded = json.dumps(payload, ensure_ascii=False)

    assert "ftp" not in payload
    assert "ULTRA_SECRET" not in encoded


def test_runtime_snapshot_helpers_never_touch_credential_store(monkeypatch):
    monkeypatch.setattr(
        ftp_credentials,
        "load_password",
        lambda *args: pytest.fail("load_password ne doit pas être appelé"),
    )
    monkeypatch.setattr(
        ftp_credentials,
        "save_password",
        lambda *args: pytest.fail("save_password ne doit pas être appelé"),
    )

    payload = project_config_to_runtime_payload(_rich_config())
    project_config_from_runtime_payload(payload)


def test_runtime_snapshot_rejects_invalid_model_before_emission():
    config = ProjectConfig()
    config.site.title = ""

    with pytest.raises(RuntimeSnapshotError, match="site.title"):
        project_config_to_runtime_payload(config)


def test_runtime_snapshot_rejects_ftp_on_reception():
    payload = project_config_to_runtime_payload(ProjectConfig())
    payload["ftp"] = {"password": "secret"}

    with pytest.raises(RuntimeSnapshotError, match="ftp"):
        project_config_from_runtime_payload(payload)


def test_runtime_snapshot_rejects_invalid_received_payload():
    payload = project_config_to_runtime_payload(ProjectConfig())
    del payload["site"]

    with pytest.raises(RuntimeSnapshotError, match="site"):
        project_config_from_runtime_payload(payload)
