from bloggen.markdown.paragraph_alignment import format_alignment_marker, strip_alignment_marker


def test_format_alignment_marker_for_non_default_alignments():
    assert format_alignment_marker("center") == "{{align=center}}"
    assert format_alignment_marker("right") == "{{align=right}}"
    assert format_alignment_marker("justify") == "{{align=justify}}"


def test_format_alignment_marker_empty_for_left_or_default():
    assert format_alignment_marker("left") == ""
    assert format_alignment_marker("") == ""


def test_format_alignment_marker_empty_for_unknown_value():
    assert format_alignment_marker("bogus") == ""


def test_strip_alignment_marker_extracts_and_removes():
    text, alignment = strip_alignment_marker("{{align=center}}Contenu.")
    assert text == "Contenu."
    assert alignment == "center"


def test_strip_alignment_marker_defaults_to_left_when_absent():
    text, alignment = strip_alignment_marker("Contenu simple.")
    assert text == "Contenu simple."
    assert alignment == "left"


def test_strip_alignment_marker_ignores_unknown_value():
    text, alignment = strip_alignment_marker("{{align=bogus}}Contenu.")
    assert text == "{{align=bogus}}Contenu."
    assert alignment == "left"
