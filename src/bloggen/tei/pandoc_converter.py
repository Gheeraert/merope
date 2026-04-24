"""Pandoc-based Markdown -> TEI conversion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from bloggen.markdown.front_matter import read_markdown_with_front_matter
from bloggen.markdown.normalizer import normalize_markdown_text
from bloggen.tei.postprocess import postprocess_tei_file
from bloggen.tei.validator import TeiValidationResult, validate_tei_file
from bloggen.utils.subprocesses import CommandNotFoundError, run_command


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
) -> MarkdownToTeiResult:
    source = Path(input_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    parsed = read_markdown_with_front_matter(source)
    normalized_body = normalize_markdown_text(parsed.body, google_docs_mode=google_docs_mode)

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
        postprocess_tei_file(destination, destination, title=title)
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
