"""Read-only diagnostic application for the real Qt/Windows clipboard."""

from __future__ import annotations

import hashlib
import platform
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from PySide6.QtCore import QMimeData, qVersion
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bloggen.ui.qt_editor.clipboard_probe_native import (
    NativeClipboardReport,
    enumerate_windows_clipboard_formats,
)


PREVIEW_LIMIT = 4000
_DATA_URI_RE = re.compile(r"data:[^\s\"'<>]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class MimeFormatProbe:
    name: str
    size_bytes: int
    sha256: str
    preview: str | None = None


@dataclass(frozen=True, slots=True)
class HtmlImageProbe:
    src_kind: str
    src: str
    alt: str | None
    width: str | None
    height: str | None
    src_length: int
    src_sha256: str


@dataclass(frozen=True, slots=True)
class ImageDataProbe:
    type_name: str
    width: int | None
    height: int | None
    image_format: str | None
    size_bytes: int | None
    convertible_to_qimage: bool


@dataclass(frozen=True, slots=True)
class UrlProbe:
    value: str
    kind: str


@dataclass(frozen=True, slots=True)
class ClipboardProbeReport:
    platform: str
    python_version: str
    qt_version: str
    formats: tuple[MimeFormatProbe, ...]
    has_text: bool
    has_html: bool
    has_image: bool
    has_urls: bool
    text_length: int | None
    text_preview: str | None
    html_length: int | None
    html_preview: str | None
    html_images: tuple[HtmlImageProbe, ...]
    image_data: ImageDataProbe | None
    urls: tuple[UrlProbe, ...]
    native: NativeClipboardReport


def _bounded_preview(value: str, *, limit: int = PREVIEW_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n[tronqué, longueur totale = {len(value)}]"


def _redact_data_uris(value: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        uri = match.group(0)
        header, separator, payload = uri.partition(",")
        if not separator:
            return f"data:<{len(uri)} caractères; sha256={_sha256_text(uri)}>"
        media_type = header[5:].split(";", 1)[0] or "type-inconnu"
        encoding = ";base64" if ";base64" in header.lower() else ""
        return (
            f"data:{media_type}{encoding},<{len(payload)} caractères; "
            f"sha256={_sha256_text(uri)}>"
        )

    return _DATA_URI_RE.sub(replacement, value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8", errors="surrogatepass"))


def classify_image_src(src: str) -> str:
    lowered = src.strip().lower()
    if not lowered:
        return "vide"
    for scheme in ("data", "https", "http", "file", "cid"):
        if lowered.startswith(f"{scheme}:"):
            return scheme
    return "autre"


def _summarize_src(src: str) -> str:
    if classify_image_src(src) != "data":
        return _bounded_preview(src, limit=1000)
    return _redact_data_uris(src)


class _ImageTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[HtmlImageProbe] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "img":
            return
        values = {str(name).lower(): value for name, value in attrs}
        src = values.get("src") or ""
        self.images.append(
            HtmlImageProbe(
                src_kind=classify_image_src(src),
                src=_summarize_src(src),
                alt=values.get("alt"),
                width=values.get("width"),
                height=values.get("height"),
                src_length=len(src),
                src_sha256=_sha256_text(src),
            )
        )


def inspect_html_images(html: str) -> tuple[HtmlImageProbe, ...]:
    parser = _ImageTagParser()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, AssertionError):
        pass
    return tuple(parser.images)


def _is_textual_format(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"text/plain", "text/html", "application/rtf", "text/rtf"} or (
        "html" in lowered or "rtf" in lowered
    )


def _format_preview(name: str, raw: bytes) -> str | None:
    if not _is_textual_format(name):
        return None
    text = raw.decode("utf-8", errors="replace").rstrip("\x00")
    if "html" in name.lower():
        text = _redact_data_uris(text)
    return _bounded_preview(text)


def _enum_name(value: object) -> str:
    name = getattr(value, "name", None)
    return str(name) if name else str(value)


def _probe_image_data(value: object) -> ImageDataProbe:
    image: QImage | None = None
    if isinstance(value, QImage):
        image = value
    elif isinstance(value, QPixmap):
        image = value.toImage()

    return ImageDataProbe(
        type_name=f"{type(value).__module__}.{type(value).__qualname__}",
        width=image.width() if image is not None else None,
        height=image.height() if image is not None else None,
        image_format=_enum_name(image.format()) if image is not None else None,
        size_bytes=int(image.sizeInBytes()) if image is not None else None,
        convertible_to_qimage=image is not None,
    )


def probe_mime_data(
    mime: QMimeData,
    *,
    native_report: NativeClipboardReport | None = None,
) -> ClipboardProbeReport:
    """Capture a bounded, non-mutating inventory of one ``QMimeData``."""

    formats: list[MimeFormatProbe] = []
    for name in mime.formats():
        raw = bytes(mime.data(name))
        formats.append(
            MimeFormatProbe(
                name=name,
                size_bytes=len(raw),
                sha256=_sha256_bytes(raw),
                preview=_format_preview(name, raw),
            )
        )

    text = mime.text() if mime.hasText() else None
    html = mime.html() if mime.hasHtml() else None
    image_data = None
    if mime.hasImage():
        try:
            image_data = _probe_image_data(mime.imageData())
        except (TypeError, RuntimeError):
            image_data = ImageDataProbe(
                type_name="indisponible",
                width=None,
                height=None,
                image_format=None,
                size_bytes=None,
                convertible_to_qimage=False,
            )

    urls = tuple(
        UrlProbe(url.toString(), "locale file://" if url.isLocalFile() else "distante")
        for url in (mime.urls() if mime.hasUrls() else [])
    )
    return ClipboardProbeReport(
        platform=platform.platform(),
        python_version=platform.python_version(),
        qt_version=qVersion(),
        formats=tuple(formats),
        has_text=mime.hasText(),
        has_html=mime.hasHtml(),
        has_image=mime.hasImage(),
        has_urls=mime.hasUrls(),
        text_length=len(text) if text is not None else None,
        text_preview=_bounded_preview(text) if text is not None else None,
        html_length=len(html) if html is not None else None,
        html_preview=_bounded_preview(_redact_data_uris(html)) if html is not None else None,
        html_images=inspect_html_images(html or ""),
        image_data=image_data,
        urls=urls,
        native=native_report or enumerate_windows_clipboard_formats(),
    )


def _bool(value: bool) -> str:
    return "true" if value else "false"


def format_probe_report(report: ClipboardProbeReport) -> str:
    lines = [
        "MÉROPE CLIPBOARD PROBE",
        "ATTENTION : ce rapport peut contenir une partie du texte copié et des URL.",
        "Vérifiez-le avant de le partager.",
        f"Platform: {report.platform}",
        f"Qt: {report.qt_version}",
        f"Python: {report.python_version}",
        "",
        "=== QMimeData ===",
        "",
        "formats:",
    ]
    if not report.formats:
        lines.append("- (aucun)")
    for item in report.formats:
        lines.extend(
            [
                f"- {item.name}",
                f"  bytes: {item.size_bytes}",
                f"  sha256: {item.sha256}",
            ]
        )
        if item.preview is not None:
            lines.extend(["  aperçu textuel:", item.preview])

    lines.extend(
        [
            "",
            f"hasText: {_bool(report.has_text)}",
            f"hasHtml: {_bool(report.has_html)}",
            f"hasImage: {_bool(report.has_image)}",
            f"hasUrls: {_bool(report.has_urls)}",
        ]
    )
    if report.text_preview is not None:
        lines.extend(
            ["", "--- text/plain ---", f"length: {report.text_length}", report.text_preview]
        )
    if report.html_preview is not None:
        lines.extend(
            [
                "",
                "--- text/html ---",
                f"length: {report.html_length}",
                f"img count: {len(report.html_images)}",
                report.html_preview,
            ]
        )
        for index, image in enumerate(report.html_images):
            lines.extend(
                [
                    "",
                    f"img[{index}]:",
                    f"  src kind: {image.src_kind}",
                    f"  src: {image.src}",
                    f"  src length: {image.src_length}",
                    f"  src sha256: {image.src_sha256}",
                    f"  alt: {image.alt!r}",
                    f"  width: {image.width!r}",
                    f"  height: {image.height!r}",
                ]
            )
    if report.urls:
        lines.extend(["", "--- URLs ---"])
        for url in report.urls:
            lines.append(f"- [{url.kind}] {url.value}")
    if report.image_data is not None:
        image = report.image_data
        lines.extend(
            [
                "",
                "--- imageData() ---",
                f"type: {image.type_name}",
                f"width: {image.width}",
                f"height: {image.height}",
                f"format: {image.image_format}",
                f"approx bytes: {image.size_bytes}",
                f"convertible to QImage: {_bool(image.convertible_to_qimage)}",
            ]
        )

    lines.extend(["", "=== Native Windows clipboard ==="])
    if not report.native.available:
        lines.append(report.native.message or "indisponible")
    else:
        for item in report.native.formats:
            size = item.size_bytes if item.size_bytes is not None else "indisponible"
            lines.append(f"- {item.format_id} {item.name}: {size} bytes")
        if not report.native.formats:
            lines.append("- (aucun)")

    return "\n".join(lines) + "\n"


class ClipboardProbeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mérope — Audit du presse-papiers")
        self.resize(900, 700)

        warning = QLabel(
            "Ce rapport peut contenir une partie du texte copié et des URL. "
            "Vérifiez-le avant de le partager."
        )
        warning.setWordWrap(True)
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText(
            "Copiez un contenu dans Word ou Chrome, puis cliquez sur Inspecter."
        )

        inspect_button = QPushButton("Inspecter le presse-papiers")
        copy_button = QPushButton("Copier le rapport")
        save_button = QPushButton("Enregistrer le rapport...")
        inspect_button.clicked.connect(self.inspect_clipboard)
        copy_button.clicked.connect(self.copy_report)
        save_button.clicked.connect(self.save_report)

        buttons = QHBoxLayout()
        buttons.addWidget(inspect_button)
        buttons.addWidget(copy_button)
        buttons.addWidget(save_button)
        buttons.addStretch(1)

        layout = QVBoxLayout()
        layout.addWidget(warning)
        layout.addLayout(buttons)
        layout.addWidget(self.report_view)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    def inspect_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        report = probe_mime_data(clipboard.mimeData())
        self.report_view.setPlainText(format_probe_report(report))

    def copy_report(self) -> None:
        QApplication.clipboard().setText(self.report_view.toPlainText())

    def save_report(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Enregistrer le rapport",
            "merope-clipboard-probe.txt",
            "Rapport texte (*.txt);;Tous les fichiers (*)",
        )
        if filename:
            Path(filename).write_text(self.report_view.toPlainText(), encoding="utf-8")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Mérope Clipboard Probe")
    window = ClipboardProbeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
