from bloggen.markdown.note_shortcuts import (
    convert_double_paren_notes_in_blocks,
    convert_double_paren_notes_in_markdown_text,
    split_double_paren_notes,
)
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun


def _registry():
    definitions: dict[str, str] = {}

    def register(text: str) -> str:
        next_id = 1
        while str(next_id) in definitions:
            next_id += 1
        note_id = str(next_id)
        definitions[note_id] = text
        return note_id

    return register, definitions


def test_double_paren_note_is_split_out_with_spacing_preserved():
    register, definitions = _registry()
    runs = [InlineRun(text="mot ((une remarque)) suite")]

    result = split_double_paren_notes(runs, register)

    assert [r.text for r in result] == ["mot ", "", " suite"]
    assert result[1].footnote_ref == "1"
    assert definitions == {"1": "une remarque"}


def test_multiple_notes_get_distinct_ids_in_order():
    register, definitions = _registry()
    runs = [InlineRun(text="a ((premiere)) b ((seconde)) c")]

    result = split_double_paren_notes(runs, register)

    refs = [r.footnote_ref for r in result if r.footnote_ref is not None]
    assert refs == ["1", "2"]
    assert definitions == {"1": "premiere", "2": "seconde"}


def test_new_ids_do_not_collide_with_existing_definitions():
    register, definitions = _registry()
    definitions["1"] = "note deja presente"
    runs = [InlineRun(text="texte ((nouvelle note)) fin")]

    result = split_double_paren_notes(runs, register)

    footnote_runs = [r for r in result if r.footnote_ref is not None]
    assert footnote_runs[0].footnote_ref == "2"


def test_single_parens_are_left_alone_only_double_parens_convert():
    register, _definitions = _registry()
    runs = [InlineRun(text="voir (a) et (b) ici, pas ((une note)) ici")]

    result = split_double_paren_notes(runs, register)

    # Only the true "((...))" pair converts; "(a)"/"(b)" (single parens) are untouched.
    assert any(r.footnote_ref is not None for r in result)
    assert "(a)" in "".join(r.text for r in result if r.footnote_ref is None)
    assert "(b)" in "".join(r.text for r in result if r.footnote_ref is None)


def test_note_immediately_followed_by_punctuation_converts():
    # Regression: an earlier version required a space on both sides of
    # "((...))", so a note placed right before the sentence's closing
    # punctuation — the most common way to actually write one — silently
    # never converted.
    register, definitions = _registry()
    runs = [InlineRun(text="Une phrase avec une note((ceci est la note)). Suite.")]

    result = split_double_paren_notes(runs, register)

    footnote_runs = [r for r in result if r.footnote_ref is not None]
    assert len(footnote_runs) == 1
    assert definitions == {"1": "ceci est la note"}
    assert "".join(r.text for r in result if r.footnote_ref is None) == "Une phrase avec une note. Suite."


def test_note_followed_by_comma_converts():
    register, definitions = _registry()
    runs = [InlineRun(text="Un mot((note)), puis la suite.")]

    result = split_double_paren_notes(runs, register)

    assert any(r.footnote_ref is not None for r in result)
    assert definitions == {"1": "note"}


def test_note_at_very_start_of_text_converts():
    register, definitions = _registry()
    runs = [InlineRun(text="((note initiale)) reste du texte")]

    result = split_double_paren_notes(runs, register)

    footnote_runs = [r for r in result if r.footnote_ref is not None]
    assert len(footnote_runs) == 1
    assert definitions == {"1": "note initiale"}


def test_bold_run_formatting_is_preserved_around_the_note():
    register, _definitions = _registry()
    runs = [InlineRun(text="mot ((note)) suite", bold=True)]

    result = split_double_paren_notes(runs, register)

    text_runs = [r for r in result if r.footnote_ref is None]
    assert all(r.bold for r in text_runs)


def test_image_and_existing_footnote_runs_are_untouched():
    register, _definitions = _registry()
    runs = [
        InlineRun(image_src="img.png", image_alt="alt"),
        InlineRun(footnote_ref="7"),
    ]

    result = split_double_paren_notes(runs, register)

    assert result == runs


def test_empty_note_text_is_not_converted():
    register, definitions = _registry()
    runs = [InlineRun(text="mot (( )) suite")]

    result = split_double_paren_notes(runs, register)

    assert not definitions
    assert "".join(r.text for r in result) == "mot (( )) suite"


def test_convert_in_blocks_recurses_into_children():
    register, definitions = _registry()
    outer = Block(kind=PARAGRAPH, runs=[])
    inner = Block(kind=PARAGRAPH, runs=[InlineRun(text="a ((note)) b")])
    outer.children = [inner]

    convert_double_paren_notes_in_blocks([outer], register)

    assert definitions == {"1": "note"}
    assert any(r.footnote_ref == "1" for r in inner.runs)


# -- convert_double_paren_notes_in_markdown_text (build-time, raw Markdown) --


def test_markdown_converts_to_pandoc_inline_footnote_syntax():
    result = convert_double_paren_notes_in_markdown_text("Un mot ((une note)) ici.")
    assert result == "Un mot ^[une note] ici."


def test_markdown_note_glued_to_punctuation_converts():
    # This is the exact scenario reported broken: a note placed right
    # before the sentence's closing period, with no trailing space at all.
    result = convert_double_paren_notes_in_markdown_text("Une phrase((la note)). Suite.")
    assert result == "Une phrase^[la note]. Suite."


def test_markdown_multiple_notes_on_one_line():
    result = convert_double_paren_notes_in_markdown_text("a((premiere)) et b((seconde)).")
    assert result == "a^[premiere] et b^[seconde]."


def test_markdown_fenced_code_block_is_left_untouched():
    text = "Avant ((une note)).\n\n```\ncode avec ((parentheses)) littérales\n```\n\nAprès.\n"
    result = convert_double_paren_notes_in_markdown_text(text)
    assert "^[une note]" in result
    assert "((parentheses))" in result
    assert "^[parentheses]" not in result


def test_markdown_inline_code_span_is_left_untouched():
    text = "Du texte `avec ((code)) inline` et une vraie note ((ceci)) ici."
    result = convert_double_paren_notes_in_markdown_text(text)
    assert "`avec ((code)) inline`" in result
    assert "^[ceci]" in result


def test_markdown_no_double_parens_is_a_no_op():
    text = "Un texte tout à fait normal, avec (une parenthèse simple).\n"
    assert convert_double_paren_notes_in_markdown_text(text) == text


def test_markdown_empty_note_text_is_left_alone():
    text = "Texte avec (( )) vide."
    assert convert_double_paren_notes_in_markdown_text(text) == text
