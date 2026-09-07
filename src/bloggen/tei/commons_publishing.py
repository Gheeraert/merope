"""Diagnostic validation of generated TEI against the TEI Commons
Publishing RelaxNG schema.

This is Phase 1 of adopting Commons Publishing (see the companion
project Mini-Métopes, C:/mini-metopes /
https://github.com/Gheeraert/mini-metopes, which already produces
valid Commons Publishing TEI from DOCX): make the gap between what
MEROPE's Pandoc-based pipeline currently emits and what the profile
actually requires visible and measurable, before attempting to close
it.

Verified directly against a real MEROPE build: Pandoc's own generic
TEI output does NOT validate against this schema out of the box (its
<div>/<p> structure doesn't match Commons Publishing's stricter
abstract model) — so this check is expected to report issues on every
build for now. That's the point: it never fails the build (see
build_site's use of this module), only makes the shortfall visible
instead of the loose well-formedness check in bloggen.tei.validator
quietly passing everything. Closing the gap for real (Phases 2-4 of
the roadmap) means enriching the teiHeader and, eventually, replacing
Pandoc's generic TEI writer with a serializer built from MEROPE's own
Block/InlineRun model — mirroring Mini-Métopes' own architecture
(editorial model -> hand-built TEI serializer, never a generic
converter) — not patching this validator.

The schema itself (resources/schemas/commons-publishing/) is copied
unmodified from Mini-Métopes, under the CeCILL-B license from the
upstream TEI Commons Publishing project (see LICENSE.txt/
PROVENANCE.json alongside it) — MEROPE's own code in this module is
original, written in the same spirit as Mini-Métopes'
src/mini_metopes/validation.py (lxml RelaxNG, compiled once, no
network/DTD resolution).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from lxml import etree

# Same convention as bloggen.build.assets.copy_builtin_resources: resolved
# relative to this file, not the current working directory, so it works
# the same whether MEROPE is run from an editable install or installed
# normally.
_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "resources"
    / "schemas"
    / "commons-publishing"
    / "commons-publishing.rng"
)


@dataclass(slots=True, frozen=True)
class CommonsPublishingIssue:
    message: str
    line: int | None = None
    column: int | None = None

    def __str__(self) -> str:
        if self.line and self.column:
            location = f"{self.line}:{self.column}"
        elif self.line:
            location = f"ligne {self.line}"
        else:
            location = "?"
        return f"{location}: {self.message}"


@dataclass(slots=True, frozen=True)
class CommonsPublishingValidationResult:
    valid: bool
    issues: tuple[CommonsPublishingIssue, ...]


def _xml_parser() -> etree.XMLParser:
    """A parser with no network access, external DTD, or entity
    resolution — the same hardening already used elsewhere in this
    pipeline (see bloggen.render.xslt_runner) for untrusted-ish XML."""
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, recover=False)


@lru_cache(maxsize=1)
def _commons_publishing_schema() -> etree.RelaxNG:
    """Loads and compiles the bundled RNG once per process, regardless
    of the current working directory."""
    schema_root = etree.fromstring(_SCHEMA_PATH.read_bytes(), parser=_xml_parser())
    return etree.RelaxNG(schema_root)


def _issue_from_error(error: etree._LogEntry) -> CommonsPublishingIssue:
    return CommonsPublishingIssue(message=error.message, line=error.line or None, column=error.column or None)


def validate_commons_publishing_bytes(data: bytes) -> CommonsPublishingValidationResult:
    """Validates TEI XML bytes against the bundled Commons Publishing
    RelaxNG schema. A syntax error in the XML itself is reported the
    same way as a schema violation — either way, "not valid Commons
    Publishing TEI" — rather than raising."""
    try:
        document = etree.fromstring(data, parser=_xml_parser())
    except etree.XMLSyntaxError as error:
        issues = tuple(_issue_from_error(item) for item in error.error_log)
        return CommonsPublishingValidationResult(valid=False, issues=issues)

    schema = _commons_publishing_schema()
    if schema.validate(document):
        return CommonsPublishingValidationResult(valid=True, issues=())
    return CommonsPublishingValidationResult(
        valid=False, issues=tuple(_issue_from_error(item) for item in schema.error_log)
    )


def validate_commons_publishing_file(path: str | Path) -> CommonsPublishingValidationResult:
    return validate_commons_publishing_bytes(Path(path).read_bytes())
