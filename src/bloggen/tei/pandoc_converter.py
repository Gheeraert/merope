"""Pandoc-based Markdown -> TEI conversion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from bloggen.markdown.front_matter import read_markdown_with_front_matter
from bloggen.markdown.image_attributes import strip_image_attributes
from bloggen.markdown.normalizer import normalize_markdown_text
from bloggen.tei.header_builder import TeiHeaderMetadata
from bloggen.tei.postprocess import (
    apply_heading_levels_in_tei_file,
    apply_image_attributes_in_tei_file,
    apply_paragraph_alignment_in_tei_file,
    extract_heading_levels,
    postprocess_tei_file,
    sanitize_link_targets_in_tei_file,
)
from bloggen.tei.validator import TeiValidationResult, validate_tei_file
from bloggen.utils.subprocesses import CommandNotFoundError, CommandTimeoutError, run_command


@dataclass(slots=True)
class PandocConversionResult:
    source_file: Path
    tei_file: Path
    command: list[str]
    success: bool
    message: str = ""


@dataclass(slots=True)
class MarkdownToTeiResult:
    source_file: Path
    tei_file: Path
    command: list[str]
    success: bool
    message: str
    validation: TeiValidationResult


# Rewrites the reserved Mérope encadré div into a native TEI Commons
# Publishing floatingText (Pandoc's TEI writer would otherwise drop it).
ENCADRE_LUA_FILTER = (
    Path(__file__).resolve().parent.parent / "resources" / "pandoc" / "merope_encadre.lua"
)


class PandocUnavailableError(RuntimeError):
    """Raised when pandoc is not available in PATH."""


def convert_markdown_to_tei(
    input_path: str | Path,
    output_path: str | Path,
    *,
    options: list[str] | None = None,
    pandoc_command: str = "pandoc",
) -> PandocConversionResult:
    source = Path(input_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    command = [
        pandoc_command,
        "--from=markdown+footnotes+pipe_tables",
        "--to=tei",
        f"--lua-filter={ENCADRE_LUA_FILTER}",
        "--standalone",
        str(source),
        "-o",
        str(destination),
    ]
    if options:
        command.extend(options)

    try:
        command_result = run_command(command)
    except CommandNotFoundError as exc:
        raise PandocUnavailableError(
            "Pandoc est introuvable. Installez Pandoc et vérifiez qu'il est accessible dans le PATH."
        ) from exc
    except CommandTimeoutError as exc:
        # An ordinary failed conversion, not a crash: build_site() already
        # routes PandocConversionResult(success=False) through its normal
        # per-item error path (report.errors), same as any other Pandoc
        # failure. A destination file Pandoc had started writing before
        # being killed on timeout is never treated as valid output — every
        # caller below only proceeds past this point when success is True.
        return PandocConversionResult(
            source_file=source,
            tei_file=destination,
            command=command,
            success=False,
            message=str(exc),
        )

    if not command_result.success:
        message = command_result.stderr.strip() or "Pandoc a échoué sans message détaillé."
        return PandocConversionResult(
            source_file=source,
            tei_file=destination,
            command=command,
            success=False,
            message=message,
        )

    return PandocConversionResult(
        source_file=source,
        tei_file=destination,
        command=command,
        success=True,
        message="Conversion Pandoc réussie.",
    )


def convert_markdown_file_to_tei(
    input_path: str | Path,
    output_path: str | Path,
    *,
    google_docs_mode: bool = True,
    pandoc_command: str = "pandoc",
    header_metadata: TeiHeaderMetadata | None = None,
) -> MarkdownToTeiResult:
    source = Path(input_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    parsed = read_markdown_with_front_matter(source)
    normalized_body = normalize_markdown_text(parsed.body, google_docs_mode=google_docs_mode)
    # Pandoc's TEI writer drops Markdown image attribute suffixes
    # (width/height/align set by the content editor), so they are stripped
    # before conversion and re-applied to the generated TEI afterwards.
    normalized_body, image_attributes = strip_image_attributes(normalized_body)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        suffix=".md",
        delete=False,
        dir=destination.parent,
    ) as handle:
        handle.write(normalized_body)
        temporary_markdown_path = Path(handle.name)

    try:
        conversion = convert_markdown_to_tei(
            temporary_markdown_path,
            destination,
            pandoc_command=pandoc_command,
        )
        if not conversion.success:
            return MarkdownToTeiResult(
                source_file=source,
                tei_file=destination,
                command=conversion.command,
                success=False,
                message=conversion.message,
                validation=TeiValidationResult(valid=False, errors=[conversion.message]),
            )

        title = parsed.metadata.get("title")
        postprocess_tei_file(destination, destination, title=title, header_metadata=header_metadata)
        heading_levels = extract_heading_levels(normalized_body)
        if heading_levels:
            apply_heading_levels_in_tei_file(destination, heading_levels)
        if image_attributes:
            apply_image_attributes_in_tei_file(destination, image_attributes)
        if "{{align=" in normalized_body:
            apply_paragraph_alignment_in_tei_file(destination)
        # Publication boundary: a Markdown source that never went through
        # the rich-text editor's own href policy (hand-written, or
        # produced by an external tool) can still carry a dangerous link
        # scheme straight through Pandoc's TEI conversion unfiltered — see
        # bloggen.tei.postprocess.sanitize_link_targets_in_tei_xml. Must
        # run before validate_tei_file/the Commons Publishing pass and
        # before this TEI is read for the sidecar or handed to the XSLT.
        sanitize_link_targets_in_tei_file(destination)
        validation = validate_tei_file(destination)

        if not validation.valid:
            message = "; ".join(validation.errors)
            return MarkdownToTeiResult(
                source_file=source,
                tei_file=destination,
                command=conversion.command,
                success=False,
                message=message,
                validation=validation,
            )

        return MarkdownToTeiResult(
            source_file=source,
            tei_file=destination,
            command=conversion.command,
            success=True,
            message="Pipeline Markdown -> TEI réussi.",
            validation=validation,
        )
    finally:
        try:
            temporary_markdown_path.unlink(missing_ok=True)
        except PermissionError:
            pass
