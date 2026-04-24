"""Build report structures and formatting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
        f"HTML générés: {len(report.generated_html)}",
        f"TEI générés: {len(report.generated_tei)}",
        f"Sortie: {report.output_dir}",
    ]
    if report.warnings:
        lines.append("Avertissements:")
        lines.extend(f"- {item}" for item in report.warnings)
    if report.errors:
        lines.append("Erreurs:")
        lines.extend(f"- {item}" for item in report.errors)
    return "\n".join(lines)
