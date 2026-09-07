from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest
from PIL import Image

from bloggen.config.models import BannerConfig
from bloggen.ui.banner_panel import BannerPanel, _copy_into_dir, _resize_banner_image


@pytest.fixture(scope="module")
def root():
    # See tests/test_menu_link_dialog.py: one Tk() reused across a module's
    # tests avoids the flakiness of rapid create/destroy churn.
    window = tk.Tk()
    window.withdraw()
    yield window
    window.destroy()


def _make_image(path: Path, size: tuple[int, int], color: str = "red") -> None:
    Image.new("RGB", size, color=color).save(path)


def test_resize_banner_image_produces_exact_target_dimensions(tmp_path: Path):
    source = tmp_path / "source.jpg"
    _make_image(source, (3000, 900))  # much wider/shorter than the target

    result = _resize_banner_image(source, 1260, 220)

    assert result.exists()
    assert result != source
    with Image.open(result) as image:
        assert image.size == (1260, 220)


def test_resize_banner_image_never_overwrites_the_source(tmp_path: Path):
    source = tmp_path / "source.png"
    _make_image(source, (400, 400))
    with Image.open(source) as before:
        original_size = before.size

    _resize_banner_image(source, 1260, 220)

    with Image.open(source) as after:
        assert after.size == original_size


def test_resize_banner_image_avoids_filename_collisions(tmp_path: Path):
    source = tmp_path / "banniere.jpg"
    _make_image(source, (2000, 500))
    (tmp_path / "banniere-banniere.jpg").write_bytes(b"already here")

    result = _resize_banner_image(source, 1260, 220)

    assert result.name != "banniere-banniere.jpg"
    assert result.exists()


def test_copy_into_dir_copies_and_creates_the_directory(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"fake image bytes")
    destination_dir = tmp_path / "assets" / "banner"

    result = _copy_into_dir(source, destination_dir)

    assert result == destination_dir / "source.jpg"
    assert result.read_bytes() == b"fake image bytes"


def test_copy_into_dir_avoids_collisions_with_a_different_file(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"new content")
    destination_dir = tmp_path / "assets" / "banner"
    destination_dir.mkdir(parents=True)
    (destination_dir / "source.jpg").write_bytes(b"unrelated existing content")

    result = _copy_into_dir(source, destination_dir)

    assert result.name == "source-2.jpg"
    assert result.read_bytes() == b"new content"


def test_copy_into_dir_is_a_no_op_when_source_is_already_the_destination(tmp_path: Path):
    destination_dir = tmp_path / "assets" / "banner"
    destination_dir.mkdir(parents=True)
    existing = destination_dir / "source.jpg"
    existing.write_bytes(b"content")

    result = _copy_into_dir(existing, destination_dir)

    assert result == existing


def test_banner_panel_height_round_trips_through_set_and_get_data(root):
    panel = BannerPanel(root)
    panel.set_data(BannerConfig(height_px=300))
    assert panel.get_data().height_px == 300


def test_banner_panel_get_data_raises_a_clean_error_on_empty_height(root):
    """height_var used to be a tk.IntVar: clearing the entry raised a raw
    tkinter.TclError on .get() instead of a catchable, friendly message —
    not caught by any of main_window.py's except (..., ValueError) clauses.
    """
    panel = BannerPanel(root)
    panel.height_var.set("")
    with pytest.raises(ValueError, match="Hauteur"):
        panel.get_data()


def test_banner_panel_get_data_raises_a_clean_error_on_non_numeric_height(root):
    panel = BannerPanel(root)
    panel.height_var.set("abc")
    with pytest.raises(ValueError, match="Hauteur"):
        panel.get_data()


def test_banner_panel_get_data_rejects_a_non_positive_height(root):
    panel = BannerPanel(root)
    panel.height_var.set("0")
    with pytest.raises(ValueError, match="supérieur ou égal à 1"):
        panel.get_data()
