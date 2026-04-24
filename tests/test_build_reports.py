from pathlib import Path

from bloggen.build.reports import BuildReport, format_build_report


def test_format_build_report_summarizes_counts_and_truncates_lists():
    report = BuildReport(
        success=True,
        output_dir=Path("site"),
        tei_dir=Path("build/tei"),
        generated_html=[Path(f"site/p{i}.html") for i in range(3)],
        generated_tei=[Path(f"build/tei/p{i}.xml") for i in range(2)],
        warnings=[f"warn-{i}" for i in range(12)] + ["Bannière désactivée: image introuvable"],
        errors=[f"err-{i}" for i in range(11)],
    )

    text = format_build_report(report)

    assert "Succès: oui" in text
    assert "HTML générés: 3" in text
    assert "TEI générés: 2" in text
    assert "Erreurs: 11" in text
    assert "Avertissements: 13" in text
    assert "Bannière: désactivée automatiquement." in text
    assert "Avertissements (aperçu):" in text
    assert "Erreurs (aperçu):" in text
    assert "- warn-9" in text
    assert "- warn-10" not in text
    assert "- err-9" in text
    assert "- err-10" not in text
    assert "- ..." in text


def test_format_build_report_mentions_media_copy_when_present():
    report = BuildReport(
        success=True,
        output_dir=Path("site"),
        tei_dir=Path("build/tei"),
        warnings=["content/posts/a.md: médias liés copiés (2)."],
    )

    text = format_build_report(report)

    assert "Médias liés: copie effectuée." in text
