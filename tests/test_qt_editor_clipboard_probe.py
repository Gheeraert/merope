from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray, QMimeData, QUrl
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from bloggen.ui.qt_editor.clipboard_probe import (
    PREVIEW_LIMIT,
    classify_image_src,
    format_probe_report,
    inspect_html_images,
    probe_mime_data,
)
from bloggen.ui.qt_editor.clipboard_probe_native import (
    NativeClipboardFormat,
    NativeClipboardReport,
    native_format_name,
)


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _native() -> NativeClipboardReport:
    return NativeClipboardReport(
        True,
        formats=(NativeClipboardFormat(13, "CF_UNICODETEXT", 42),),
    )


def test_probe_plain_text_is_bounded_and_does_not_mutate_mime():
    mime = QMimeData()
    value = "x" * (PREVIEW_LIMIT + 25)
    mime.setText(value)
    before_formats = mime.formats()
    before_data = {name: bytes(mime.data(name)) for name in before_formats}

    report = probe_mime_data(mime, native_report=_native())

    assert report.has_text
    assert not report.has_html
    assert report.text_length == len(value)
    assert "[tronqué, longueur totale" in report.text_preview
    assert mime.formats() == before_formats
    assert {name: bytes(mime.data(name)) for name in before_formats} == before_data


def test_probe_html_only_finds_and_classifies_images():
    mime = QMimeData()
    mime.setHtml(
        '<p>Avant<img src="file:///C:/photo.png" alt="Fichier" width="20" height="10">'
        '<img src="https://example.org/photo.jpg" alt="Web"><img src="cid:image1"></p>'
    )

    report = probe_mime_data(mime, native_report=_native())

    assert report.has_html
    assert not report.has_text
    assert [image.src_kind for image in report.html_images] == ["file", "https", "cid"]
    assert report.html_images[0].alt == "Fichier"
    assert report.html_images[0].width == "20"
    assert report.html_images[0].height == "10"


def test_data_uri_is_summarized_and_never_dumped():
    payload = "QUJD" * 2000
    uri = f"data:image/png;base64,{payload}"
    mime = QMimeData()
    mime.setHtml(f'<p><img src="{uri}" alt="Image"></p>')

    report = probe_mime_data(mime, native_report=_native())
    formatted = format_probe_report(report)

    image = report.html_images[0]
    assert image.src_kind == "data"
    assert image.src_length == len(uri)
    assert image.src.startswith("data:image/png;base64,<8000 caractères; sha256=")
    assert payload not in image.src
    assert payload not in report.html_preview
    assert payload not in formatted


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("", "vide"),
        ("data:image/png;base64,AA==", "data"),
        ("http://example.org/a", "http"),
        ("https://example.org/a", "https"),
        ("file:///tmp/a", "file"),
        ("cid:a", "cid"),
        ("relative/a.png", "autre"),
    ],
)
def test_classify_image_src(src, expected):
    assert classify_image_src(src) == expected


def test_probe_qimage_records_dimensions_format_and_size():
    mime = QMimeData()
    image = QImage(17, 9, QImage.Format.Format_ARGB32)
    image.fill(0xFF123456)
    mime.setImageData(image)

    report = probe_mime_data(mime, native_report=_native())

    assert report.has_image
    assert report.image_data is not None
    assert report.image_data.type_name.endswith("QImage")
    assert (report.image_data.width, report.image_data.height) == (17, 9)
    assert report.image_data.image_format == "Format_ARGB32"
    assert report.image_data.size_bytes == image.sizeInBytes()
    assert report.image_data.convertible_to_qimage


def test_probe_urls_distinguishes_local_and_remote():
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("C:/images/a.png"), QUrl("https://example.org/a")])

    report = probe_mime_data(mime, native_report=_native())

    assert report.has_urls
    assert [item.kind for item in report.urls] == ["locale file://", "distante"]
    assert report.urls[1].value == "https://example.org/a"


def test_custom_binary_format_has_only_size_and_stable_hash():
    mime = QMimeData()
    payload = b"\x00\x01\xffsecret-binary"
    mime.setData("application/x-example-binary", QByteArray(payload))

    first = probe_mime_data(mime, native_report=_native())
    second = probe_mime_data(mime, native_report=_native())
    item = first.formats[0]

    assert item.size_bytes == len(payload)
    assert item.preview is None
    assert item.sha256 == second.formats[0].sha256
    assert "secret-binary" not in format_probe_report(first)


def test_windows_named_html_format_gets_redacted_text_preview():
    payload = b'<img src="data:image/png;base64,QUJDREVGRw==">'
    mime = QMimeData()
    mime.setData(
        'application/x-qt-windows-mime;value="HTML Format"',
        QByteArray(payload),
    )

    report = probe_mime_data(mime, native_report=_native())

    assert report.formats[0].preview is not None
    assert "QUJDREVGRw==" not in report.formats[0].preview
    assert "data:image/png;base64,<12 caractères" in report.formats[0].preview


def test_inspect_html_images_tolerates_empty_src_and_keeps_hash():
    images = inspect_html_images('<img src="" alt="Vide"><IMG src="relative.png">')
    assert images[0].src_kind == "vide"
    assert images[0].alt == "Vide"
    assert len(images[0].src_sha256) == 64
    assert images[1].src_kind == "autre"


def test_formatted_report_contains_qt_and_native_sections():
    mime = QMimeData()
    mime.setText("Bossuet")
    report = probe_mime_data(mime, native_report=_native())

    text = format_probe_report(report)

    assert text.startswith("MÉROPE CLIPBOARD PROBE")
    assert "Vérifiez-le avant de le partager" in text
    assert "=== QMimeData ===" in text
    assert "text/plain" in text
    assert "=== Native Windows clipboard ===" in text
    assert "13 CF_UNICODETEXT: 42 bytes" in text


def test_native_format_names_cover_standard_registered_and_unknown():
    assert native_format_name(2) == "CF_BITMAP"
    assert native_format_name(0xC001, "HTML Format") == "HTML Format"
    assert native_format_name(999) == "format-999"
