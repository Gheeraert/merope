from __future__ import annotations

from datetime import datetime

import pytest
from PIL import Image

from bloggen.content import image_service


@pytest.mark.parametrize("mode", ["RGB", "L", "RGBA", "LA"])
def test_adjust_image_identity_preserves_mode_and_pixels(mode):
    color = {
        "RGB": (80, 120, 160),
        "L": 100,
        "RGBA": (80, 120, 160, 73),
        "LA": (100, 73),
    }[mode]
    source = Image.new(mode, (3, 2), color)

    adjusted = image_service.adjust_image(source)

    assert adjusted is not source
    assert adjusted.mode == mode
    assert adjusted.tobytes() == source.tobytes()


@pytest.mark.parametrize(
    ("brightness", "comparison"),
    [(50, lambda value: value > 100), (-50, lambda value: value < 100)],
)
def test_adjust_image_brightness_changes_luminance(brightness, comparison):
    adjusted = image_service.adjust_image(
        Image.new("L", (1, 1), 100),
        brightness=brightness,
    )

    assert comparison(adjusted.getpixel((0, 0)))


def test_adjust_image_contrast_expands_or_compresses_a_known_range():
    source = Image.new("L", (3, 1))
    source.putdata([40, 120, 200])

    increased = image_service.adjust_image(source, contrast=50)
    decreased = image_service.adjust_image(source, contrast=-50)

    assert increased.getpixel((0, 0)) < source.getpixel((0, 0))
    assert increased.getpixel((2, 0)) > source.getpixel((2, 0))
    assert decreased.getpixel((0, 0)) > source.getpixel((0, 0))
    assert decreased.getpixel((2, 0)) < source.getpixel((2, 0))


@pytest.mark.parametrize("mode", ["RGBA", "LA"])
def test_adjust_image_preserves_alpha_byte_for_byte(mode):
    source = Image.new(mode, (4, 1))
    if mode == "RGBA":
        source.putdata([(40, 80, 120, alpha) for alpha in (0, 17, 128, 255)])
    else:
        source.putdata([(80, alpha) for alpha in (0, 17, 128, 255)])

    adjusted = image_service.adjust_image(source, brightness=70, contrast=-30)

    assert adjusted.getchannel("A").tobytes() == source.getchannel("A").tobytes()


def test_adjust_image_converts_transparent_palette_without_losing_alpha():
    source = Image.new("P", (2, 1))
    source.putpalette([0, 0, 0, 200, 100, 50] + [0, 0, 0] * 254)
    source.putdata([0, 1])
    source.info["transparency"] = bytes([0, 255])

    adjusted = image_service.adjust_image(source, brightness=50)

    assert adjusted.mode == "RGBA"
    assert adjusted.getchannel("A").tobytes() == bytes([0, 255])


def test_adjust_image_converts_opaque_palette_to_rgb():
    source = Image.new("P", (1, 1))
    source.putpalette([20, 40, 60] + [0, 0, 0] * 255)

    adjusted = image_service.adjust_image(source, contrast=20)

    assert adjusted.mode == "RGB"


@pytest.mark.parametrize("value", [-100, 100])
def test_adjust_image_accepts_slider_bounds(value):
    result = image_service.adjust_image(
        Image.new("RGB", (1, 1), "gray"),
        brightness=value,
        contrast=value,
    )

    assert result.size == (1, 1)


@pytest.mark.parametrize("value", [-101, 101, True, False, 1.5, "1"])
def test_adjust_image_rejects_invalid_slider_values(value):
    with pytest.raises(ValueError):
        image_service.adjust_image(Image.new("RGB", (1, 1)), brightness=value)
    with pytest.raises(ValueError):
        image_service.adjust_image(Image.new("RGB", (1, 1)), contrast=value)


def test_write_adjusted_copy_keeps_source_and_numbers_without_suffix_chains(tmp_path):
    source = tmp_path / "assets" / "photo.png"
    source.parent.mkdir()
    Image.new("RGB", (10, 8), (80, 100, 120)).save(source)
    original = source.read_bytes()
    Image.new("RGB", (1, 1)).save(source.with_name("photo-adjust1.png"))

    first_src = image_service.write_adjusted_copy(
        source,
        tmp_path,
        brightness=20,
        contrast=10,
    )
    first = tmp_path / first_src
    second_src = image_service.write_adjusted_copy(
        first,
        tmp_path,
        brightness=-20,
        contrast=5,
    )

    assert first.name == "photo-adjust2.png"
    assert (tmp_path / second_src).name == "photo-adjust3.png"
    assert source.read_bytes() == original
    with Image.open(first) as adjusted:
        assert adjusted.size == (10, 8)

    cropped = source.with_name("photo-crop2.png")
    Image.new("RGB", (2, 2), "gray").save(cropped)
    cropped_src = image_service.write_adjusted_copy(
        cropped,
        tmp_path,
        brightness=10,
        contrast=0,
    )
    assert (tmp_path / cropped_src).name == "photo-crop2-adjust1.png"


def test_write_adjusted_copy_preserves_png_alpha_and_jpeg_profile(tmp_path):
    png = tmp_path / "logo.png"
    rgba = Image.new("RGBA", (3, 1))
    rgba.putdata([(20, 40, 60, alpha) for alpha in (0, 127, 255)])
    rgba.save(png)
    png_src = image_service.write_adjusted_copy(
        png,
        tmp_path,
        brightness=30,
        contrast=20,
    )
    with Image.open(tmp_path / png_src) as adjusted_png:
        assert adjusted_png.getchannel("A").tobytes() == rgba.getchannel("A").tobytes()

    jpeg = tmp_path / "photo.jpg"
    Image.new("RGB", (20, 10), "gray").save(jpeg, icc_profile=b"profile")
    jpeg_src = image_service.write_adjusted_copy(
        jpeg,
        tmp_path,
        brightness=10,
        contrast=-10,
    )
    with Image.open(tmp_path / jpeg_src) as adjusted_jpeg:
        assert adjusted_jpeg.size == (20, 10)
        assert adjusted_jpeg.info.get("icc_profile") == b"profile"


def test_write_adjusted_copy_applies_exif_orientation(tmp_path):
    source = tmp_path / "phone.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (40, 20), "gray").save(source, exif=exif)

    result = image_service.write_adjusted_copy(
        source,
        tmp_path,
        brightness=10,
        contrast=0,
    )

    with Image.open(tmp_path / result) as adjusted:
        assert adjusted.size == (20, 40)
        assert adjusted.getexif().get(0x0112) in (None, 1)


def test_write_adjusted_copy_identity_creates_no_asset(tmp_path):
    source = tmp_path / "photo.png"
    Image.new("RGB", (2, 2), "gray").save(source)

    result = image_service.write_adjusted_copy(
        source,
        tmp_path,
        brightness=0,
        contrast=0,
    )

    assert result == "photo.png"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["photo.png"]


def test_write_adjusted_copy_removes_candidate_after_save_failure(tmp_path, monkeypatch):
    source = tmp_path / "photo.png"
    Image.new("RGB", (2, 2), "gray").save(source)

    def fail_save(_image, destination, **_kwargs):
        destination.write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(image_service, "_save_like_source", fail_save)

    with pytest.raises(OSError, match="disk full"):
        image_service.write_adjusted_copy(
            source,
            tmp_path,
            brightness=10,
            contrast=0,
        )
    assert sorted(path.name for path in tmp_path.iterdir()) == ["photo.png"]


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


def test_cropping_a_crop_does_not_chain_suffixes(tmp_path):
    source = tmp_path / "photo-crop2.png"
    Image.new("RGB", (10, 8), color="red").save(source)
    (tmp_path / "photo-crop1.png").write_bytes(b"x")

    result = image_service.write_cropped_copy(source, (0, 0, 5, 5), tmp_path)

    assert result == "photo-crop3.png"


def test_crop_keeps_png_transparency_and_releases_the_source(tmp_path):
    source = tmp_path / "logo.png"
    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    image.putpixel((5, 5), (255, 0, 0, 255))
    image.save(source)

    result = image_service.write_cropped_copy(source, (2, 2, 8, 8), tmp_path)

    with Image.open(tmp_path / result) as cropped:
        assert cropped.mode == "RGBA"
        assert cropped.getpixel((0, 0)) == (0, 0, 0, 0)
        assert cropped.getpixel((3, 3)) == (255, 0, 0, 255)
    source.unlink()  # would fail on Windows if a handle were left open


def test_jpeg_crop_is_reencoded_at_high_quality_with_icc_profile(tmp_path):
    source = tmp_path / "photo.jpg"
    noise = Image.effect_noise((64, 64), 80).convert("RGB")
    noise.save(source, quality=95, icc_profile=b"fake-profile")

    result = image_service.write_cropped_copy(source, (0, 0, 64, 32), tmp_path)

    reference = tmp_path / "reference-q75.jpg"
    noise.crop((0, 0, 64, 32)).save(reference)  # Pillow's default quality
    with Image.open(tmp_path / result) as cropped, Image.open(reference) as default:
        assert cropped.size == (64, 32)
        assert cropped.info.get("icc_profile") == b"fake-profile"
        assert max(cropped.quantization[0]) * 3 < max(default.quantization[0])


def test_crop_box_refers_to_exif_oriented_then_rotated_pixels(tmp_path):
    source = tmp_path / "phone.jpg"
    raw = Image.new("RGB", (40, 20), "white")
    raw.paste((255, 0, 0), (0, 0, 10, 20))  # red band on the stored left side
    exif = Image.Exif()
    exif[0x0112] = 6  # stored sideways: displayed rotated 90° clockwise
    raw.save(source, exif=exif, quality=95)

    assert image_service.probe_image(source) == (20, 40)
    assert image_service.edited_size(source, quarter_turns=1) == (40, 20)

    top_band = image_service.write_cropped_copy(source, (0, 0, 20, 10), tmp_path)
    with Image.open(tmp_path / top_band) as cropped:
        assert cropped.size == (20, 10)
        red, green, blue = cropped.getpixel((10, 5))
        assert red > 200 and green < 60 and blue < 60
        assert cropped.getexif().get(0x0112) in (None, 1)

    turned = image_service.write_cropped_copy(
        source, (0, 0, 40, 20), tmp_path, quarter_turns=1
    )
    with Image.open(tmp_path / turned) as rotated:
        assert rotated.size == (40, 20)


def test_invalid_box_is_rejected_before_any_file_is_written(tmp_path):
    source = tmp_path / "image.png"
    Image.new("RGB", (10, 8)).save(source)

    for box in ((0, 0, 11, 8), (5, 0, 5, 8), (0, 0, 10.0, 8)):
        try:
            image_service.write_cropped_copy(source, box, tmp_path)
        except ValueError:
            pass
        else:  # pragma: no cover - explicit failure message
            raise AssertionError(f"boîte acceptée : {box}")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["image.png"]


def test_crop_is_identity_only_for_full_unrotated_box(tmp_path):
    source = tmp_path / "image.png"
    Image.new("RGB", (10, 8)).save(source)

    assert image_service.crop_is_identity(source, (0, 0, 10, 8))
    assert not image_service.crop_is_identity(source, (0, 0, 10, 7))
    assert not image_service.crop_is_identity(source, (0, 0, 8, 10), quarter_turns=1)


def test_probe_is_cached_until_the_file_changes(tmp_path, monkeypatch):
    source = tmp_path / "image.png"
    Image.new("RGB", (10, 8)).save(source)
    assert image_service.probe_image(source) == (10, 8)

    opened = []
    real_open = image_service.Image.open
    monkeypatch.setattr(
        image_service.Image,
        "open",
        lambda *args, **kwargs: opened.append(args) or real_open(*args, **kwargs),
    )
    assert image_service.probe_image(source) == (10, 8)
    assert opened == []

    Image.new("RGB", (30, 20)).save(source)
    import os

    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert image_service.probe_image(source) == (30, 20)
    assert len(opened) == 1
    assert image_service.probe_image(tmp_path / "absent.png") is None
    (tmp_path / "broken.png").write_bytes(b"not an image")
    assert image_service.probe_image(tmp_path / "broken.png") is None


def test_oriented_preview_is_reduced_and_reports_full_size(tmp_path):
    source = tmp_path / "big.jpg"
    Image.new("RGB", (3000, 1500), "navy").save(source)

    preview, full_size = image_service.load_oriented_preview(source, 600)

    assert full_size == (3000, 1500)
    assert max(preview.size) <= 600
    assert preview.mode == "RGBA"


def test_load_image_or_placeholder_is_gui_independent(tmp_path):
    missing = image_service.load_image_or_placeholder(tmp_path / "missing.png")

    assert missing.size == (200, 150)
    assert missing.getpixel((0, 0)) == (204, 204, 204)
