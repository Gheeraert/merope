from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from bloggen.config.models import TopBannerConfig
from bloggen.ui import top_banner_panel
from bloggen.ui.top_banner_panel import TopBannerPanel


@pytest.fixture(scope="module")
def root(tk_root):
    return tk_root


def test_top_banner_panel_defaults_and_set_get(root, tmp_path):
    panel = TopBannerPanel(root, resolve_assets_root=lambda: (tmp_path, "assets"))
    assert panel.get_data() == TopBannerConfig()

    values = TopBannerConfig(
        enabled=True,
        image="assets/top-banner/institution.png",
        alt="Université & institut",
        link="https://example.org/",
    )
    panel.set_data(values)
    assert panel.get_data() == values
    panel.destroy()


def test_browse_copies_exact_image_bytes_and_avoids_collision(root, tmp_path, monkeypatch):
    source = tmp_path / "original" / "institution.png"
    source.parent.mkdir()
    Image.new("RGB", (1000, 200), color="blue").save(source)
    original_bytes = source.read_bytes()

    destination = tmp_path / "project" / "assets" / "top-banner"
    destination.mkdir(parents=True)
    (destination / "institution.png").write_bytes(b"existing image")

    panel = TopBannerPanel(root, resolve_assets_root=lambda: (tmp_path / "project", "assets"))
    seen_filetypes = []

    def choose_image(**kwargs):
        seen_filetypes.extend(kwargs["filetypes"])
        return str(source)

    monkeypatch.setattr(top_banner_panel.filedialog, "askopenfilename", choose_image)
    monkeypatch.setattr(
        top_banner_panel.messagebox,
        "askyesno",
        lambda *args, **kwargs: pytest.fail("Le bandeau supérieur ne doit pas proposer de redimensionnement"),
    )

    panel._browse_image()

    copied = destination / "institution-2.png"
    assert panel.get_data().image == "assets/top-banner/institution-2.png"
    assert copied.read_bytes() == original_bytes
    assert source.read_bytes() == original_bytes
    assert (destination / "institution.png").read_bytes() == b"existing image"
    with Image.open(copied) as image:
        assert image.size == (1000, 200)
    patterns = " ".join(pattern for _, pattern in seen_filetypes)
    for extension in ("png", "jpg", "jpeg", "gif", "webp"):
        assert f"*.{extension}" in patterns
    panel.destroy()
