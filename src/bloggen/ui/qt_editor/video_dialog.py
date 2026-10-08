"""Small modal dialog asking for a YouTube URL, an optional caption and a
display width; also used, prefilled, to edit an existing video block."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bloggen.markdown.video_syntax import (
    DEFAULT_WIDTH,
    MAX_WIDTH,
    MIN_WIDTH,
    parse_youtube_url,
    youtube_watch_url,
)


class VideoInsertDialog(QDialog):
    """Collect a YouTube URL (required), a caption and a width (optional).

    The URL is parsed and strictly validated on "OK" (see
    :func:`bloggen.markdown.video_syntax.parse_youtube_url`); an invalid
    URL is reported inline and keeps the dialog open rather than closing
    it on bad input.

    Passing ``video_id`` prefills the dialog for editing an existing video
    (the URL field shows its canonical watch URL) and retitles it
    accordingly; the field stays a plain URL field, so re-submitting it
    goes through the exact same validation as a fresh insertion.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        video_id: str | None = None,
        caption: str = "",
        width: int = DEFAULT_WIDTH,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modifier la vidéo" if video_id is not None else "Insérer une vidéo")
        self._video_id: str | None = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.url_edit = QLineEdit(self)
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self.url_edit.setToolTip("URL YouTube (watch, youtu.be, embed ou shorts)")
        if video_id is not None:
            self.url_edit.setText(youtube_watch_url(video_id))
        form.addRow("URL YouTube :", self.url_edit)
        self.caption_edit = QLineEdit(self)
        self.caption_edit.setPlaceholderText("Facultatif")
        self.caption_edit.setToolTip("Légende de la vidéo (facultative)")
        self.caption_edit.setText(caption)
        form.addRow("Légende :", self.caption_edit)
        self.width_spin = QSpinBox(self)
        self.width_spin.setRange(MIN_WIDTH, MAX_WIDTH)
        self.width_spin.setSingleStep(5)
        self.width_spin.setSuffix(" %")
        self.width_spin.setValue(width)
        self.width_spin.setToolTip(
            f"Largeur d’affichage, en pourcentage de la colonne ({MIN_WIDTH}–{MAX_WIDTH} %)"
        )
        form.addRow("Largeur :", self.width_spin)
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

    def width(self) -> int:
        """The chosen display width, as a percentage of the column."""

        return self.width_spin.value()
