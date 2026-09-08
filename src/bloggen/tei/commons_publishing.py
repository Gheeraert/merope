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

This validates both the RelaxNG grammar and the schema's embedded
Schematron assertions (9 <sch:assert>/<sch:report> rules, extracted via
lxml.isoschematron.extract_rng — see _commons_publishing_schematron).
One of those assertions and one rule context use an XPath 2.0-only
comparison operator (`gt`, `eq`); lxml's Schematron support is built on
libxslt's XSLT 1.0 engine, which rejects them outright at compile time.
Both are rewritten to their XPath 1.0 equivalent (`>`, `=`) before
compiling — a value-preserving substitution for the singleton-scalar
comparisons these particular rules make, done in memory against the
extracted copy only; the bundled .rng file itself, and its recorded
sha256 in PROVENANCE.json, are untouched. A future update to the
upstream schema could introduce more such operators (or genuinely
XPath-2-only constructs a `>`-style rewrite can't fix) and make this
extraction fail to compile again — see _REWRITTEN_XPATH2_OPERATORS.

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
import re

from lxml import etree, isoschematron

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


# See this module's docstring: two of the 9 Schematron rules embedded in
# the bundled RNG use an XPath 2.0-only comparison operator (`gt`, `eq`)
# that libxslt's XSLT 1.0 engine — what lxml.isoschematron compiles
# against — refuses outright. Both instances here are singleton-scalar
# comparisons (`string-length(...) gt 0`, `@type eq 'deprecationInfo'`),
# for which the XPath 1.0 operator is exactly equivalent, not just a
# closest approximation.
_XPATH2_COMPARISON_OPERATOR_RE = re.compile(r"(?<=[\s(])(gt|lt|ge|le|eq|ne)(?=[\s)])")
_XPATH1_COMPARISON_OPERATORS = {"gt": ">", "lt": "<", "ge": ">=", "le": "<=", "eq": "=", "ne": "!="}
_SVRL_NS = "http://purl.oclc.org/dsdl/svrl"


def _rewrite_xpath2_comparison_operators(schematron_root: etree._Element) -> None:
    for element in schematron_root.iter():
        for attribute in ("context", "test", "select"):
            value = element.get(attribute)
            if value is None:
                continue
            padded = f" {value} "
            rewritten = _XPATH2_COMPARISON_OPERATOR_RE.sub(
                lambda match: _XPATH1_COMPARISON_OPERATORS[match.group(1)], padded
            ).strip()
            if rewritten != value:
                element.set(attribute, rewritten)


@lru_cache(maxsize=1)
def _commons_publishing_schematron() -> isoschematron.Schematron:
    """Extracts and compiles the Schematron assertions embedded in the
    bundled RNG, once per process. ASSERTS_AND_REPORTS so a <sch:report>
    (fires when its test is true — i.e. a problem was found, the
    opposite polarity of <sch:assert>) is caught too, not just outright
    assertion failures; both represent a genuine constraint violation
    regardless of the role="nonfatal" some of these rules carry (that
    only means "not fatal to Schematron processing itself", not "safe to
    ignore" — see _issues_from_svrl, which surfaces it in the message)."""
    schema_root = etree.fromstring(_SCHEMA_PATH.read_bytes(), parser=_xml_parser())
    extracted = isoschematron.extract_rng(schema_root)
    _rewrite_xpath2_comparison_operators(extracted)
    return isoschematron.Schematron(
        extracted, error_finder=isoschematron.Schematron.ASSERTS_AND_REPORTS, store_report=True
    )


def _issues_from_svrl(report: etree._Element) -> tuple[CommonsPublishingIssue, ...]:
    """Schematron failures carry an XPath location, not a line/column —
    folded into the message text instead, since CommonsPublishingIssue's
    line/column fields are RelaxNG/XML-syntax concepts."""
    issues = []
    for node in report.iter(f"{{{_SVRL_NS}}}failed-assert", f"{{{_SVRL_NS}}}successful-report"):
        text_element = node.find(f"{{{_SVRL_NS}}}text")
        raw_message = (text_element.text or "").strip() if text_element is not None else ""
        message = re.sub(r"\s+", " ", raw_message) or "(règle Schematron sans message)"
        if node.get("role") == "nonfatal":
            message = f"[avertissement] {message}"
        location = node.get("location")
        if location:
            message = f"{message} [{location}]"
        issues.append(CommonsPublishingIssue(message=message))
    return tuple(issues)


def validate_commons_publishing_bytes(data: bytes) -> CommonsPublishingValidationResult:
    """Validates TEI XML bytes against the bundled Commons Publishing
    schema — both its RelaxNG grammar and its embedded Schematron
    assertions (see _commons_publishing_schematron). A syntax error in
    the XML itself is reported the same way as a schema violation —
    either way, "not valid Commons Publishing TEI" — rather than
    raising."""
    try:
        document = etree.fromstring(data, parser=_xml_parser())
    except etree.XMLSyntaxError as error:
        issues = tuple(_issue_from_error(item) for item in error.error_log)
        return CommonsPublishingValidationResult(valid=False, issues=issues)

    schema = _commons_publishing_schema()
    relaxng_issues = (
        () if schema.validate(document) else tuple(_issue_from_error(item) for item in schema.error_log)
    )

    schematron = _commons_publishing_schematron()
    schematron_issues = () if schematron.validate(document) else _issues_from_svrl(schematron.validation_report)

    issues = relaxng_issues + schematron_issues
    return CommonsPublishingValidationResult(valid=not issues, issues=issues)


def validate_commons_publishing_file(path: str | Path) -> CommonsPublishingValidationResult:
    return validate_commons_publishing_bytes(Path(path).read_bytes())
