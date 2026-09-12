from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMimeData, QUrl
from PySide6.QtGui import QImage, QPixmap, QTextCursor
from PySide6.QtWidgets import QApplication

from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.clipboard_images import inspect_html_image_markup
from bloggen.ui.qt_editor.clipboard_fragment import MEROPE_FRAGMENT_MIME
from bloggen.ui.qt_editor.document_adapter import extract_blocks, populate_document
from bloggen.ui.qt_editor import text_edit as text_edit_module
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.window import QtEditorWindow


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()


def _qimage(width: int = 8, height: int = 6, color: int = 0xFF336699) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color)
    return image


def _png_bytes() -> bytes:
    payload = QBuffer()
    payload.open(QIODevice.OpenModeFlag.WriteOnly)
    assert _qimage().save(payload, "PNG")
    return bytes(payload.data())


def _write_png(path: Path, *, color: int = 0xFF336699) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    assert _qimage(color=color).save(str(path), "PNG")


def _editor(
    tmp_path: Path,
    blocks: list[Block] | None = None,
    *,
    with_context: bool = True,
) -> tuple[MeropeTextEdit, Path, Path]:
    editor = MeropeTextEdit()
    populate_document(editor.document(), blocks or [])
    editor.document().setModified(False)
    doc_dir = tmp_path / "project" / "content" / "pages"
    images_dir = tmp_path / "project" / "assets" / "images"
    doc_dir.mkdir(parents=True, exist_ok=True)
    if with_context:
        editor.set_external_paste_context(images_dir=images_dir, doc_dir=doc_dir)
    return editor, doc_dir, images_dir


def _asset_files(images_dir: Path) -> list[Path]:
    if not images_dir.exists():
        return []
    return sorted(path for path in images_dir.iterdir() if path.is_file())


def _staging_dirs(images_dir: Path) -> list[Path]:
    if not images_dir.exists():
        return []
    return list(images_dir.glob(".merope-paste-*"))


def _image_runs(editor: MeropeTextEdit) -> list[InlineRun]:
    return [
        run
        for block in extract_blocks(editor.document())
        for run in block.runs
        if run.image_src is not None
    ]


def _paste_html(editor: MeropeTextEdit, html: str, *, text: str = "fallback") -> list[str]:
    mime = QMimeData()
    mime.setHtml(html)
    mime.setText(text)
    refused: list[str] = []
    editor.pasteRefused.connect(refused.append)
    editor.insertFromMimeData(mime)
    return refused


def test_data_uri_image_keeps_position_metadata_and_one_undo(tmp_path):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Document")])]
    editor, doc_dir, images_dir = _editor(tmp_path, original)
    cursor = QTextCursor(editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    payload = base64.b64encode(_png_bytes()).decode("ascii")
    html = (
        '<p>Avant<img src="data:image/png;base64,'
        f'{payload}" alt="Bossuet" width="320" height="180">Après</p>'
    )

    assert _paste_html(editor, html) == []

    pasted = extract_blocks(editor.document())
    images = _image_runs(editor)
    assert len(images) == 1
    assert images[0].image_alt == "Bossuet"
    assert images[0].image_width == "320"
    assert images[0].image_height == "180"
    assert [run.text for run in pasted[0].runs if run.image_src is None] == ["DocumentAvant", "Après"]
    final_path = (doc_dir / images[0].image_src).resolve()
    assert final_path.parent == images_dir.resolve()
    assert final_path.read_bytes().startswith(b"\x89PNG")
    assert _staging_dirs(images_dir) == []

    editor.undo()
    assert extract_blocks(editor.document()) == original
    assert final_path.exists()
    editor.redo()
    assert extract_blocks(editor.document()) == pasted


class _FakeHeaders:
    def get_content_type(self):
        return "image/png"


class _FakeResponse:
    def __init__(self, data: bytes):
        self.data = data
        self.headers = _FakeHeaders()

    def read(self, size=-1):
        return self.data[:size] if size >= 0 else self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeOpener:
    def __init__(self, data: bytes | None = None, error: Exception | None = None):
        self.data = data
        self.error = error

    def open(self, url, timeout=None):
        if self.error:
            raise self.error
        return _FakeResponse(self.data)


def test_http_image_success_uses_shared_downloader(tmp_path, monkeypatch):
    from bloggen.markdown import html_paste_import

    monkeypatch.setattr(html_paste_import, "_is_safe_remote_host", lambda host: True)
    monkeypatch.setattr(
        html_paste_import,
        "_build_image_opener",
        lambda: _FakeOpener(_png_bytes()),
    )
    editor, doc_dir, images_dir = _editor(tmp_path)

    assert _paste_html(editor, '<p><img src="https://example.org/a.png"></p>') == []

    image = _image_runs(editor)[0]
    assert (doc_dir / image.image_src).resolve().is_file()
    assert len(_asset_files(images_dir)) == 1
    assert _staging_dirs(images_dir) == []


def test_http_failure_is_atomic_and_leaves_no_asset_or_staging(tmp_path, monkeypatch):
    from bloggen.markdown import html_paste_import

    monkeypatch.setattr(html_paste_import, "_is_safe_remote_host", lambda host: True)
    monkeypatch.setattr(
        html_paste_import,
        "_build_image_opener",
        lambda: _FakeOpener(error=OSError("network down")),
    )
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Document intact")])]
    editor, _doc_dir, images_dir = _editor(tmp_path, original)
    cursor = QTextCursor(editor.document())
    cursor.setPosition(2)
    cursor.setPosition(7, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    before_selection = (cursor.anchor(), cursor.position())

    refused = _paste_html(
        editor,
        '<p>Avant<img src="https://example.org/missing.png">Après</p>',
    )

    assert refused
    assert extract_blocks(editor.document()) == original
    assert (editor.textCursor().anchor(), editor.textCursor().position()) == before_selection
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    assert _asset_files(images_dir) == []
    assert _staging_dirs(images_dir) == []


def test_unsupported_structure_after_image_removes_staging_and_keeps_document(tmp_path):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Intact")])]
    editor, _doc_dir, images_dir = _editor(tmp_path, original)
    payload = base64.b64encode(_png_bytes()).decode()
    html = (
        f'<p><img src="data:image/png;base64,{payload}"></p>'
        "<table><tr><td>Perdu</td></tr></table>"
    )

    refused = _paste_html(editor, html)

    assert refused and "<table>" in refused[0]
    assert extract_blocks(editor.document()) == original
    assert _asset_files(images_dir) == []
    assert _staging_dirs(images_dir) == []


def test_file_uri_is_validated_and_copied_with_relative_src(tmp_path):
    source = tmp_path / "outside" / "photo.png"
    _write_png(source)
    editor, doc_dir, images_dir = _editor(tmp_path)

    refused = _paste_html(
        editor,
        f'<p><img src="{source.resolve().as_uri()}" alt="Locale"></p>',
    )

    assert refused == []
    image = _image_runs(editor)[0]
    assert image.image_alt == "Locale"
    assert not Path(image.image_src).is_absolute()
    assert (doc_dir / image.image_src).resolve().parent == images_dir.resolve()


@pytest.mark.parametrize("uri", ["file:///missing/image.png", "file://server/share/image.png"])
def test_missing_or_unc_file_uri_is_refused_atomically(tmp_path, uri):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Intact")])]
    editor, _doc_dir, images_dir = _editor(tmp_path, original)

    refused = _paste_html(editor, f'<p><img src="{uri}" alt="Perdue"></p>')

    assert refused
    assert extract_blocks(editor.document()) == original
    assert _asset_files(images_dir) == []
    assert _staging_dirs(images_dir) == []


def test_fake_png_file_uri_is_refused(tmp_path):
    source = tmp_path / "outside" / "fake.png"
    source.parent.mkdir()
    source.write_text("not an image", encoding="utf-8")
    editor, _doc_dir, images_dir = _editor(tmp_path)

    refused = _paste_html(editor, f'<img src="{source.resolve().as_uri()}">')

    assert refused
    assert extract_blocks(editor.document()) == []
    assert _asset_files(images_dir) == []


def test_native_qimage_becomes_project_png_and_canonical_run(tmp_path):
    editor, doc_dir, images_dir = _editor(tmp_path)
    mime = QMimeData()
    mime.setImageData(_qimage(11, 7))

    assert editor.canInsertFromMimeData(mime)
    editor.insertFromMimeData(mime)

    image = _image_runs(editor)[0]
    final_path = (doc_dir / image.image_src).resolve()
    assert image.image_alt == ""
    assert final_path.parent == images_dir.resolve()
    loaded = QImage(str(final_path))
    assert (loaded.width(), loaded.height()) == (11, 7)


def test_native_qpixmap_is_converted_to_project_png(tmp_path):
    editor, doc_dir, _images_dir = _editor(tmp_path)
    mime = QMimeData()
    mime.setImageData(QPixmap.fromImage(_qimage(13, 5)))

    editor.insertFromMimeData(mime)

    image = _image_runs(editor)[0]
    loaded = QImage(str((doc_dir / image.image_src).resolve()))
    assert (loaded.width(), loaded.height()) == (13, 5)


def test_html_single_unresolved_image_uses_native_qimage_at_its_position(tmp_path):
    editor, _doc_dir, images_dir = _editor(tmp_path)
    mime = QMimeData()
    mime.setHtml('<p>Avant<img src="cid:image1" alt="Interne">Après</p>')
    mime.setImageData(_qimage())

    editor.insertFromMimeData(mime)

    block = extract_blocks(editor.document())[0]
    assert [run.text for run in block.runs if run.image_src is None] == ["Avant", "Après"]
    assert _image_runs(editor)[0].image_alt == "Interne"
    assert len(_asset_files(images_dir)) == 1


def test_two_html_images_cannot_share_one_native_fallback(tmp_path):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Intact")])]
    editor, _doc_dir, images_dir = _editor(tmp_path, original)
    mime = QMimeData()
    mime.setHtml('<p><img src="cid:one"><img src="cid:two"></p>')
    mime.setImageData(_qimage())
    refused = []
    editor.pasteRefused.connect(refused.append)

    editor.insertFromMimeData(mime)

    assert refused
    assert extract_blocks(editor.document()) == original
    assert _asset_files(images_dir) == []
    assert _staging_dirs(images_dir) == []


def test_vml_image_is_imported_and_keeps_simple_alt(tmp_path):
    source = tmp_path / "word" / "clip.png"
    _write_png(source)
    editor, _doc_dir, _images_dir = _editor(tmp_path)
    html = (
        '<p>Avant<v:shape><v:imagedata src="'
        f'{source.resolve().as_uri()}" o:title="Word image"></v:imagedata>'
        "</v:shape>Après</p>"
    )

    assert _paste_html(editor, html) == []

    block = extract_blocks(editor.document())[0]
    assert [run.text for run in block.runs if run.image_src is None] == ["Avant", "Après"]
    assert _image_runs(editor)[0].image_alt == "Word image"


def test_consecutive_img_and_vml_same_source_are_deduplicated(tmp_path):
    source = tmp_path / "word" / "same.png"
    _write_png(source)
    uri = source.resolve().as_uri()
    editor, _doc_dir, images_dir = _editor(tmp_path)
    html = f'<p><img src="{uri}"><v:shape><v:imagedata src="{uri}"></v:imagedata></v:shape></p>'

    assert _paste_html(editor, html) == []

    assert len(_image_runs(editor)) == 1
    assert len(_asset_files(images_dir)) == 1


def test_single_and_multiple_local_url_images(tmp_path):
    first = tmp_path / "drop" / "one.png"
    second = tmp_path / "drop" / "two.png"
    _write_png(first)
    _write_png(second, color=0xFF996633)
    editor, _doc_dir, images_dir = _editor(tmp_path)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(first)), QUrl.fromLocalFile(str(second))])

    assert editor.canInsertFromMimeData(mime)
    editor.insertFromMimeData(mime)

    blocks = extract_blocks(editor.document())
    assert len(blocks) == 2
    assert all(block.kind == PARAGRAPH for block in blocks)
    assert len(_image_runs(editor)) == 2
    assert len(_asset_files(images_dir)) == 2


def test_mixed_local_urls_fall_back_to_plain_text_without_partial_assets(tmp_path):
    image = tmp_path / "drop" / "one.png"
    other = tmp_path / "drop" / "document.pdf"
    _write_png(image)
    other.write_bytes(b"%PDF")
    editor, _doc_dir, images_dir = _editor(tmp_path)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(image)), QUrl.fromLocalFile(str(other))])
    mime.setText("Deux fichiers")

    editor.insertFromMimeData(mime)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Deux fichiers")])
    ]
    assert _asset_files(images_dir) == []
    assert _staging_dirs(images_dir) == []


def test_local_url_batch_failure_without_text_is_atomic(tmp_path):
    class UrlOnlyMimeData(QMimeData):
        def hasText(self):
            return False

    image = tmp_path / "drop" / "one.png"
    other = tmp_path / "drop" / "fake.png"
    _write_png(image)
    other.write_text("not image", encoding="utf-8")
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Intact")])]
    editor, _doc_dir, images_dir = _editor(tmp_path, original)
    mime = UrlOnlyMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(image)), QUrl.fromLocalFile(str(other))])
    refused = []
    editor.pasteRefused.connect(refused.append)

    editor.insertFromMimeData(mime)

    assert refused
    assert extract_blocks(editor.document()) == original
    assert _asset_files(images_dir) == []
    assert _staging_dirs(images_dir) == []


def test_image_paste_without_document_context_is_refused_but_text_html_works(tmp_path):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Intact")])]
    editor, _doc_dir, _images_dir = _editor(tmp_path, original, with_context=False)

    refused = _paste_html(editor, f'<img src="data:image/png;base64,{base64.b64encode(_png_bytes()).decode()}">')
    assert refused and "document Mérope" in refused[0]
    assert extract_blocks(editor.document()) == original

    cursor = QTextCursor(editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    assert _paste_html(editor, "<p><b> riche</b></p>") == []
    assert extract_blocks(editor.document())[0].runs[-1].bold


def test_native_image_without_document_context_is_refused(tmp_path):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Intact")])]
    editor, _doc_dir, images_dir = _editor(tmp_path, original, with_context=False)
    mime = QMimeData()
    mime.setImageData(_qimage())
    refused = []
    editor.pasteRefused.connect(refused.append)

    editor.insertFromMimeData(mime)

    assert refused
    assert extract_blocks(editor.document()) == original
    assert _asset_files(images_dir) == []


def test_asset_collision_uses_shared_dash_number_rule(tmp_path):
    source = tmp_path / "drop" / "photo.png"
    _write_png(source)
    editor, _doc_dir, images_dir = _editor(tmp_path)
    images_dir.mkdir(parents=True)
    (images_dir / "photo.png").write_bytes(b"existing")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])

    editor.insertFromMimeData(mime)

    assert Path(_image_runs(editor)[0].image_src).name == "photo-2.png"
    assert (images_dir / "photo.png").read_bytes() == b"existing"
    assert (images_dir / "photo-2.png").is_file()


def test_html_is_preferred_over_native_image(tmp_path):
    editor, _doc_dir, images_dir = _editor(tmp_path)
    payload = base64.b64encode(_png_bytes()).decode()
    mime = QMimeData()
    mime.setHtml(f'<p>Position<img src="data:image/png;base64,{payload}" alt="HTML"></p>')
    mime.setImageData(_qimage(color=0xFF000000))

    editor.insertFromMimeData(mime)

    assert _image_runs(editor)[0].image_alt == "HTML"
    assert len(_asset_files(images_dir)) == 1


def test_internal_merope_mime_remains_first_priority_over_html_and_qimage(tmp_path):
    editor, _doc_dir, images_dir = _editor(tmp_path, with_context=False)
    mime = QMimeData()
    mime.setData(MEROPE_FRAGMENT_MIME, QByteArray(b"**Interne**\n"))
    mime.setHtml('<p><img src="cid:external"></p>')
    mime.setImageData(_qimage())

    editor.insertFromMimeData(mime)

    assert extract_blocks(editor.document()) == [
        Block(kind=PARAGRAPH, runs=[InlineRun(text="Interne", bold=True)])
    ]
    assert _asset_files(images_dir) == []


def test_image_inventory_counts_simple_vml_and_duplicates():
    inventory = inspect_html_image_markup(
        '<img src="same"><v:imagedata src="same"><img src=""><img src="">'
    )
    assert inventory.sources == ("same", "same", "", "")
    assert inventory.semantic_image_count == 3


def test_adapter_insertion_failure_rolls_back_committed_asset(tmp_path, monkeypatch):
    original = [Block(kind=PARAGRAPH, runs=[InlineRun(text="Intact")])]
    editor, _doc_dir, images_dir = _editor(tmp_path, original)
    payload = base64.b64encode(_png_bytes()).decode()
    refused = []
    editor.pasteRefused.connect(refused.append)
    monkeypatch.setattr(
        text_edit_module,
        "insert_blocks",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("insertion")),
    )

    _paste_html(editor, f'<img src="data:image/png;base64,{payload}">')

    assert refused
    assert extract_blocks(editor.document()) == original
    assert _asset_files(images_dir) == []
    assert _staging_dirs(images_dir) == []


def test_window_load_sets_and_failed_load_keeps_external_paste_context(tmp_path):
    project = tmp_path / "project"
    content = project / "content" / "pages"
    images_dir = project / "assets" / "images"
    content.mkdir(parents=True)
    first = content / "first.md"
    first.write_text("---\ntitle: Premier\nslug: premier\n---\n\nTexte\n", encoding="utf-8")
    incompatible = content / "bad.md"
    incompatible.write_text(
        "---\ntitle: Mauvais\nslug: mauvais\n---\n\n##### Titre non pris en charge\n",
        encoding="utf-8",
    )
    window = QtEditorWindow(markdown_path=first, images_dir=images_dir)

    assert window.editor._external_paste_context is not None
    assert window.editor._external_paste_context.doc_dir == first.parent
    previous = window.editor._external_paste_context
    with pytest.raises(ValueError):
        window.load_markdown(incompatible)
    assert window.editor._external_paste_context == previous

    window.autosave_timer.stop()
    window.ipc_bridge.shutdown()
    window.deleteLater()
    QApplication.processEvents()
