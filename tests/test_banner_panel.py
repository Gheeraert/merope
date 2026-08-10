from __future__ import annotations

from pathlib import Path

from PIL import Image

from bloggen.ui.banner_panel import _copy_into_dir, _resize_banner_image


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
