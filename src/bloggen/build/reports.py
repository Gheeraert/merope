"""Build report structures and formatting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_MAX_REPORTED_ISSUES = 10


@dataclass(slots=True)
class BuildReport:
    success: bool
    output_dir: Path
    tei_dir: Path
    generated_html: list[Path] = field(default_factory=list)
    generated_tei: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def format_build_report(report: BuildReport) -> str:
    lines = [
        f"Succès: {'oui' if report.success else 'non'}",
        f"Sortie: {report.output_dir}",
        f"HTML générés: {len(report.generated_html)}",
        f"TEI générés: {len(report.generated_tei)}",
        f"Erreurs: {len(report.errors)}",
        f"Avertissements: {len(report.warnings)}",
    ]

    if any("Bannière désactivée" in item for item in report.warnings):
        lines.append("Bannière: désactivée automatiquement.")
    if any("médias liés copiés" in item for item in report.warnings):
        lines.append("Médias liés: copie effectuée.")

    if report.warnings:
        lines.append("Avertissements (aperçu):")
        lines.extend(f"- {item}" for item in report.warnings[:_MAX_REPORTED_ISSUES])
        if len(report.warnings) > _MAX_REPORTED_ISSUES:
            lines.append("- ...")
    if report.errors:
        lines.append("Erreurs (aperçu):")
        lines.extend(f"- {item}" for item in report.errors[:_MAX_REPORTED_ISSUES])
        if len(report.errors) > _MAX_REPORTED_ISSUES:
            lines.append("- ...")
    return "\n".join(lines)
