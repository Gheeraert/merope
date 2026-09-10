from __future__ import annotations

from datetime import datetime

from PIL import Image

from bloggen.content import image_service


def test_copy_into_images_dir_uses_markdown_relative_path(tmp_path):
    source = tmp_path / "source" / "illustration.png"
    source.parent.mkdir()
    source.write_bytes(b"image-data")
    images_dir = tmp_path / "assets" / "images"
    doc_dir = tmp_path / "content" / "posts"

    result = image_service.copy_into_images_dir(source, images_dir, doc_dir)

    assert result == "../../assets/images/illustration.png"
    assert (images_dir / "illustration.png").read_bytes() == b"image-data"


def test_copy_into_images_dir_avoids_collision_and_accepts_existing_target(tmp_path):
    images_dir = tmp_path / "assets" / "images"
    images_dir.mkdir(parents=True)
    existing = images_dir / "illustration.png"
    existing.write_bytes(b"old")
    source = tmp_path / "incoming" / "illustration.png"
    source.parent.mkdir()
    source.write_bytes(b"new")

    result = image_service.copy_into_images_dir(source, images_dir, tmp_path)
    same_file_result = image_service.copy_into_images_dir(existing, images_dir, tmp_path)

    assert result == "assets/images/illustration-2.png"
    assert (images_dir / "illustration-2.png").read_bytes() == b"new"
    assert same_file_result == "assets/images/illustration.png"
    assert existing.read_bytes() == b"old"


def test_calculate_display_size_preserves_existing_editor_rules():
    assert image_service.calculate_display_size((1200, 600)) == (240, 120)
    assert image_service.calculate_display_size((1200, 600), size_preset="moyen") == (420, 210)
    assert image_service.calculate_display_size((1200, 600), size_preset="original") == (1200, 600)
    assert image_service.calculate_display_size((1200, 600), width=333, height=111) == (333, 111)
    assert image_service.calculate_display_size((120, 60), size_preset="grand") == (120, 60)


def test_save_clipboard_image_uses_numbered_collision_suffix(tmp_path, monkeypatch):
    class FixedDatetime:
        @staticmethod
        def now():
            return datetime(2026, 9, 10, 12, 34, 56)

    monkeypatch.setattr(image_service, "datetime", FixedDatetime)
    images_dir = tmp_path / "assets" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "presse-papiers-20260910-123456.png").write_bytes(b"old")

    result = image_service.save_clipboard_image(
        Image.new("CMYK", (4, 3)), images_dir, tmp_path / "content" / "pages"
    )

    assert result == "../../assets/images/presse-papiers-20260910-123456-2.png"
    with Image.open(images_dir / "presse-papiers-20260910-123456-2.png") as saved:
        assert saved.size == (4, 3)
        assert saved.mode == "RGBA"


def test_write_cropped_copy_keeps_original_and_numbers_copies(tmp_path):
    source = tmp_path / "assets" / "image.png"
    source.parent.mkdir()
    Image.new("RGB", (10, 8), color="red").save(source)
    existing_crop = source.with_name("image-crop1.png")
    Image.new("RGB", (1, 1), color="blue").save(existing_crop)

    result = image_service.write_cropped_copy(source, (2, 1, 8, 6), tmp_path)

    assert result == "assets/image-crop2.png"
    with Image.open(source) as original:
        assert original.size == (10, 8)
    with Image.open(source.with_name("image-crop2.png")) as cropped:
        assert cropped.size == (6, 5)


def test_load_image_or_placeholder_is_gui_independent(tmp_path):
    missing = image_service.load_image_or_placeholder(tmp_path / "missing.png")

    assert missing.size == (200, 150)
    assert missing.getpixel((0, 0)) == (204, 204, 204)
