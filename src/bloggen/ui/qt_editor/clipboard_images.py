"""Transactional external-image clipboard import for the Qt editor."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
import warnings
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage, QPixmap

from bloggen.content.image_service import copy_into_images_dir
from bloggen.markdown.html_paste_import import html_to_blocks, resolve_image_src
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.document_adapter import validate_blocks


MAX_LOCAL_IMAGE_BYTES = 25 * 1024 * 1024
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_FORMAT_SUFFIXES = {
    "JPEG": {".jpg", ".jpeg"},
    "PNG": {".png"},
    "GIF": {".gif"},
    "WEBP": {".webp"},
    "BMP": {".bmp"},
}
_NON_IMAGE_REJECTED_TAGS = frozenset({"pre", "table"})
_LEGACY_IMAGE_REJECTED_TAGS = frozenset(
    {"img", "pre", "table", "v:imagedata", "v:shape"}
)


class ClipboardImagePasteError(ValueError):
    """Raised before insertion when an external image cannot be preserved."""


@dataclass(frozen=True, slots=True)
class ExternalPasteContext:
    images_dir: Path
    doc_dir: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "images_dir", Path(self.images_dir))
        object.__setattr__(self, "doc_dir", Path(self.doc_dir))


@dataclass(frozen=True, slots=True)
class HtmlImageInventory:
    sources: tuple[str, ...]
    has_vml_shape: bool
    unknown_vml_tags: tuple[str, ...]

    @property
    def has_image_markup(self) -> bool:
        return bool(self.sources or self.has_vml_shape)

    @property
    def semantic_image_count(self) -> int:
        deduplicated: list[str] = []
        for source in self.sources:
            if source and deduplicated and deduplicated[-1] == source:
                continue
            deduplicated.append(source)
        return len(deduplicated)


class _HtmlImageScanner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: list[str] = []
        self.has_vml_shape = False
        self.unknown_vml_tags: set[str] = set()

    def handle_starttag(self, tag: str, attrs) -> None:
        self._handle_tag(tag, attrs)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self._handle_tag(tag, attrs)

    def _handle_tag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        values = {str(name).lower(): value or "" for name, value in attrs}
        if tag in {"img", "v:imagedata"}:
            self.sources.append(values.get("src", ""))
        elif tag == "v:shape":
            self.has_vml_shape = True
        elif tag.startswith("v:"):
            self.unknown_vml_tags.add(tag)


def inspect_html_image_markup(html: str) -> HtmlImageInventory:
    scanner = _HtmlImageScanner()
    scanner.feed(html)
    scanner.close()
    return HtmlImageInventory(
        sources=tuple(scanner.sources),
        has_vml_shape=scanner.has_vml_shape,
        unknown_vml_tags=tuple(sorted(scanner.unknown_vml_tags)),
    )


@dataclass(slots=True)
class PreparedExternalPaste:
    """Validated blocks plus staged assets not yet committed to the project."""

    blocks: list[Block]
    context: ExternalPasteContext | None = None
    staging_dir: Path | None = None
    remove_images_dir_if_empty: bool = False
    _created_files: list[Path] = field(default_factory=list)
    _accepted: bool = False

    def commit_assets(self) -> list[Block]:
        if self.staging_dir is None:
            return self.blocks

        mapping: dict[Path, str] = {}
        try:
            for run in _iter_image_runs(self.blocks):
                source = _staged_source_path(
                    run.image_src,
                    staging_dir=self.staging_dir,
                    doc_dir=self.context.doc_dir,
                )
                if source not in mapping:
                    existing_files = {
                        path.resolve()
                        for path in self.context.images_dir.iterdir()
                        if path.is_file()
                    }
                    final_src = copy_into_images_dir(
                        source,
                        self.context.images_dir,
                        self.context.doc_dir,
                    )
                    final_path = (self.context.doc_dir / final_src).resolve()
                    mapping[source] = final_src
                    if final_path not in existing_files:
                        self._created_files.append(final_path)
            committed = _rewrite_staged_sources(
                self.blocks,
                mapping,
                staging_dir=self.staging_dir,
                doc_dir=self.context.doc_dir,
            )
            validate_blocks(committed)
            return committed
        except Exception:
            self.rollback()
            raise

    def accept(self) -> None:
        self._accepted = True
        self._cleanup_staging()

    def rollback(self) -> None:
        if not self._accepted:
            for path in reversed(self._created_files):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        self._created_files.clear()
        self._cleanup_staging()

    def discard(self) -> None:
        self.rollback()

    def _cleanup_staging(self) -> None:
        if self.staging_dir is not None:
            shutil.rmtree(self.staging_dir, ignore_errors=True)
            if self.remove_images_dir_if_empty:
                _remove_empty_directory(self.context.images_dir)
            self.staging_dir = None


def prepare_external_paste(
    source: QMimeData,
    context: ExternalPasteContext | None,
    *,
    html_importer: Callable[..., list[Block]] = html_to_blocks,
) -> PreparedExternalPaste | None:
    """Prepare the highest-priority external MIME representation available."""

    if source.hasHtml() and source.html().strip():
        html = source.html()
        inventory = inspect_html_image_markup(html)
        if not inventory.has_image_markup:
            blocks = html_importer(html, reject_tags=_LEGACY_IMAGE_REJECTED_TAGS)
            validate_blocks(blocks)
            return PreparedExternalPaste(blocks)
        if context is None:
            raise ClipboardImagePasteError(
                "Ouvrez ou créez d’abord un document Mérope afin de déterminer "
                "où enregistrer les images collées."
            )
        if inventory.unknown_vml_tags:
            tags = ", ".join(f"<{tag}>" for tag in inventory.unknown_vml_tags)
            raise ClipboardImagePasteError(
                f"Le presse-papiers contient une structure VML non prise en charge : {tags}"
            )
        if inventory.has_vml_shape and not inventory.sources:
            raise ClipboardImagePasteError(
                "La forme VML fournie par Word ne contient aucune image récupérable."
            )
        return _prepare_html_with_images(
            source,
            html,
            inventory,
            context,
            html_importer=html_importer,
        )

    if source.hasImage():
        if context is None:
            raise ClipboardImagePasteError(
                "Ouvrez ou créez d’abord un document Mérope afin de déterminer "
                "où enregistrer les images collées."
            )
        return _prepare_native_image(source, context)

    if source.hasUrls() and source.urls():
        urls = source.urls()
        if not all(url.isLocalFile() for url in urls):
            return None
        if context is None:
            raise ClipboardImagePasteError(
                "Ouvrez ou créez d’abord un document Mérope afin de déterminer "
                "où enregistrer les images collées."
            )
        try:
            return _prepare_local_urls(urls, context)
        except ClipboardImagePasteError:
            if source.hasText():
                return None
            raise

    return None


def _prepare_html_with_images(
    source: QMimeData,
    html: str,
    inventory: HtmlImageInventory,
    context: ExternalPasteContext,
    *,
    html_importer: Callable[..., list[Block]],
) -> PreparedExternalPaste:
    staging, remove_images_dir_if_empty = _create_staging(context.images_dir)
    cache: dict[str, str | None] = {}
    fallback_src = None
    try:
        if inventory.semantic_image_count == 1 and source.hasImage():
            fallback_src = _stage_qimage(source.imageData(), staging, context.doc_dir)

        def resolver(src: str) -> str | None:
            if src in cache:
                return cache[src]
            resolved = resolve_image_src(src, staging, context.doc_dir)
            if resolved is None and src.strip().lower().startswith("file:"):
                try:
                    resolved = _stage_file_uri(src, staging, context.doc_dir)
                except ClipboardImagePasteError:
                    if fallback_src is None:
                        raise
            if resolved is None:
                resolved = fallback_src
            if (
                resolved is None
                and source.hasImage()
                and inventory.semantic_image_count > 1
            ):
                raise ClipboardImagePasteError(
                    "Le presse-papiers contient plusieurs images dont la "
                    "correspondance avec l’image Qt native est ambiguë."
                )
            if resolved is None and src.strip().lower().startswith(
                ("http:", "https:")
            ):
                raise ClipboardImagePasteError(
                    "L’image distante annoncée dans le HTML n’a pas pu être récupérée."
                )
            cache[src] = resolved
            return resolved

        blocks = html_importer(
            html,
            images_dir=staging,
            doc_dir=context.doc_dir,
            reject_tags=_NON_IMAGE_REJECTED_TAGS,
            image_src_resolver=resolver,
            strict_images=True,
            allow_vml_images=True,
            reject_unknown_vml=True,
            preserve_image_dimensions=True,
            deduplicate_images=True,
        )
        validate_blocks(blocks)
        return PreparedExternalPaste(
            blocks=blocks,
            context=context,
            staging_dir=staging,
            remove_images_dir_if_empty=remove_images_dir_if_empty,
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if remove_images_dir_if_empty:
            _remove_empty_directory(context.images_dir)
        raise


def _prepare_native_image(
    source: QMimeData,
    context: ExternalPasteContext,
) -> PreparedExternalPaste:
    staging, remove_images_dir_if_empty = _create_staging(context.images_dir)
    try:
        image_src = _stage_qimage(source.imageData(), staging, context.doc_dir)
        blocks = [
            Block(
                kind=PARAGRAPH,
                runs=[InlineRun(image_src=image_src, image_alt="")],
            )
        ]
        validate_blocks(blocks)
        return PreparedExternalPaste(
            blocks=blocks,
            context=context,
            staging_dir=staging,
            remove_images_dir_if_empty=remove_images_dir_if_empty,
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if remove_images_dir_if_empty:
            _remove_empty_directory(context.images_dir)
        raise


def _prepare_local_urls(
    urls: list[QUrl],
    context: ExternalPasteContext,
) -> PreparedExternalPaste:
    staging, remove_images_dir_if_empty = _create_staging(context.images_dir)
    try:
        blocks = []
        for url in urls:
            source = Path(url.toLocalFile())
            image_src = _stage_local_image(source, staging, context.doc_dir)
            blocks.append(
                Block(
                    kind=PARAGRAPH,
                    runs=[InlineRun(image_src=image_src, image_alt="")],
                )
            )
        validate_blocks(blocks)
        return PreparedExternalPaste(
            blocks=blocks,
            context=context,
            staging_dir=staging,
            remove_images_dir_if_empty=remove_images_dir_if_empty,
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if remove_images_dir_if_empty:
            _remove_empty_directory(context.images_dir)
        raise


def _create_staging(images_dir: Path) -> tuple[Path, bool]:
    images_dir = Path(images_dir)
    created_images_dir = not images_dir.exists()
    try:
        images_dir.mkdir(parents=True, exist_ok=True)
        return (
            Path(tempfile.mkdtemp(prefix=".merope-paste-", dir=images_dir)),
            created_images_dir,
        )
    except OSError as exc:
        raise ClipboardImagePasteError(
            "Le répertoire d’images du projet n’est pas accessible."
        ) from exc


def _stage_qimage(value: object, staging: Path, doc_dir: Path) -> str:
    if isinstance(value, QImage):
        image = value
    elif isinstance(value, QPixmap):
        image = value.toImage()
    else:
        raise ClipboardImagePasteError(
            "L’image native du presse-papiers n’est pas convertible en QImage."
        )
    if image.isNull():
        raise ClipboardImagePasteError("L’image native du presse-papiers est vide.")

    destination = staging / f"collage-{uuid.uuid4().hex[:8]}.png"
    if not image.save(str(destination), "PNG"):
        raise ClipboardImagePasteError(
            "L’image native du presse-papiers n’a pas pu être enregistrée en PNG."
        )
    if destination.stat().st_size > MAX_LOCAL_IMAGE_BYTES:
        destination.unlink(missing_ok=True)
        raise ClipboardImagePasteError("L’image du presse-papiers dépasse 25 Mo.")
    return _relative_src(destination, doc_dir)


def _stage_file_uri(uri: str, staging: Path, doc_dir: Path) -> str:
    url = QUrl(uri)
    if url.scheme().lower() != "file" or url.host():
        raise ClipboardImagePasteError(
            "L’image file:// fournie par Word n’est pas un fichier local autorisé."
        )
    local_file = url.toLocalFile()
    if not local_file:
        raise ClipboardImagePasteError(
            "L’image locale fournie par Word ne peut pas être résolue."
        )
    return _stage_local_image(Path(local_file), staging, doc_dir)


def _stage_local_image(source: Path, staging: Path, doc_dir: Path) -> str:
    _validate_local_raster(source)
    return copy_into_images_dir(source, staging, doc_dir)


def _validate_local_raster(source: Path) -> None:
    try:
        if not source.is_file():
            raise ClipboardImagePasteError(
                "Le fichier image local fourni par le presse-papiers n’existe pas."
            )
        if source.stat().st_size > MAX_LOCAL_IMAGE_BYTES:
            raise ClipboardImagePasteError("L’image locale dépasse 25 Mo.")
    except OSError as exc:
        raise ClipboardImagePasteError(
            "Impossible de lire le fichier image local fourni par le presse-papiers."
        ) from exc

    suffix = source.suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ClipboardImagePasteError(
            "Le fichier local n’utilise pas un format raster autorisé."
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                image_format = image.format
                image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, Warning) as exc:
        raise ClipboardImagePasteError(
            "Le fichier local fourni n’est pas une image raster lisible."
        ) from exc
    if suffix not in _FORMAT_SUFFIXES.get(str(image_format).upper(), set()):
        raise ClipboardImagePasteError(
            "Le contenu du fichier image ne correspond pas à son extension."
        )


def _relative_src(path: Path, doc_dir: Path) -> str:
    return Path(os.path.relpath(path, doc_dir)).as_posix()


def _iter_image_runs(blocks: Iterable[Block]):
    for block in blocks:
        for run in block.runs:
            if run.image_src is not None:
                yield run
        yield from _iter_image_runs(block.children)


def _staged_source_path(
    image_src: str | None,
    *,
    staging_dir: Path,
    doc_dir: Path,
) -> Path:
    if not image_src:
        raise ClipboardImagePasteError("Une image préparée ne possède pas de source.")
    try:
        source = (doc_dir / image_src).resolve()
        source.relative_to(staging_dir.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        raise ClipboardImagePasteError(
            "Une source image préparée sort du staging de collage."
        ) from exc
    if not source.is_file():
        raise ClipboardImagePasteError("Une image préparée a disparu avant le collage.")
    return source


def _rewrite_staged_sources(
    blocks: list[Block],
    mapping: dict[Path, str],
    *,
    staging_dir: Path,
    doc_dir: Path,
) -> list[Block]:
    rewritten = []
    for block in blocks:
        runs = []
        for run in block.runs:
            if run.image_src is None:
                runs.append(replace(run))
                continue
            source = _staged_source_path(
                run.image_src,
                staging_dir=staging_dir,
                doc_dir=doc_dir,
            )
            runs.append(replace(run, image_src=mapping[source]))
        rewritten.append(
            replace(
                block,
                runs=runs,
                children=_rewrite_staged_sources(
                    block.children,
                    mapping,
                    staging_dir=staging_dir,
                    doc_dir=doc_dir,
                ),
            )
        )
    return rewritten


def _remove_empty_directory(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass
