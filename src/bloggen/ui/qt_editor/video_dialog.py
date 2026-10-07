"""Small modal dialog asking for a YouTube URL and an optional caption."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from bloggen.markdown.video_syntax import parse_youtube_url


class VideoInsertDialog(QDialog):
    """Collect a YouTube URL (required) and a caption (optional).

    The URL is parsed and strictly validated on "OK" (see
    :func:`bloggen.markdown.video_syntax.parse_youtube_url`); an invalid
    URL is reported inline and keeps the dialog open rather than closing
    it on bad input.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insérer une vidéo")
        self._video_id: str | None = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.url_edit = QLineEdit(self)
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self.url_edit.setToolTip("URL YouTube (watch, youtu.be, embed ou shorts)")
        form.addRow("URL YouTube :", self.url_edit)
        self.caption_edit = QLineEdit(self)
        self.caption_edit.setPlaceholderText("Facultatif")
        self.caption_edit.setToolTip("Légende de la vidéo (facultative)")
        form.addRow("Légende :", self.caption_edit)
        layout.addLayout(form)

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _validate_and_accept(self) -> None:
        video_id = parse_youtube_url(self.url_edit.text())
        if video_id is None:
            self.error_label.setText(
                "URL YouTube non reconnue. Formes acceptées : "
                "watch?v=…, youtu.be/…, embed/… ou shorts/…."
            )
            self.error_label.show()
            return
        self._video_id = video_id
        self.accept()

    def video_id(self) -> str:
        """The validated YouTube video id. Only meaningful after an
        ``Accepted`` result."""

        assert self._video_id is not None
        return self._video_id

    def caption(self) -> str:
        """The caption, single-lined and stripped; empty means none."""

        return " ".join(self.caption_edit.text().split())
