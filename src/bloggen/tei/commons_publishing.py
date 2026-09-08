"""Diagnostic validation of generated TEI against the TEI Commons
Publishing RelaxNG schema.

Status, as of the phase 2/3 work (teiHeader enrichment, then replacing
Pandoc's div/@type="levelN" with the profile's own "sectionN" — see the
commit history and bloggen.tei.postprocess): ordinary editorial content
(headings up to 6 levels deep via '#'-style Markdown, paragraphs,
lists, blockquotes, tables, footnotes, links, figures, inline
formatting) now validates. Three Markdown constructs remain outside
what this profile can represent and are known to still fail validation
when present: fenced code blocks, horizontal rules, and Setext-style
headings ("Titre\\n===", as opposed to "# Titre") — see
bloggen.tei.postprocess's module docstring for the first two, and its
_HEADING_LINE_RE for why the third isn't picked up by the heading-depth
fixup. None of this is enforced: a page using any of the three still
builds successfully, with only a warning (see build_site's use of this
module) — "validate_commons_publishing" is named and worded as a
diagnostic precisely because it does not gate the build.

This also validates the RelaxNG grammar only. The bundled schema embeds
Schematron assertions (<sch:rule>/<sch:assert>) for constraints the
grammar alone can't express — lxml's etree.RelaxNG does not evaluate
those, so a document could pass this check while still violating one of
them. Nothing here currently runs a Schematron pass against the schema.

The schema itself (resources/schemas/commons-publishing/) is copied
from the companion project Mini-Métopes (C:/mini-metopes /
https://github.com/Gheeraert/mini-metopes, which already produces
valid Commons Publishing TEI from DOCX) under the CeCILL-B license from
the upstream TEI Commons Publishing project (see LICENSE.txt/
PROVENANCE.json alongside it) — Mini-Métopes' own copy carries local,
additive extensions for its own decision 0037 contract (see
PROVENANCE.json's local_modifications_description); MEROPE's simple
<text><body> documents never exercise them, but "the bundled schema"
is accordingly a local variant, not a byte-for-byte copy of the
upstream release. MEROPE's own code in this module is original, written
in the same spirit as Mini-Métopes' src/mini_metopes/validation.py
(lxml RelaxNG, compiled once, no network/DTD resolution).
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
    schema's RelaxNG grammar only (see this module's docstring: the
    schema's embedded Schematron assertions are not evaluated). A syntax
    error in the XML itself is reported the same way as a schema
    violation — either way, "not valid Commons Publishing TEI" — rather
    than raising."""
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
