from bloggen.markdown.note_shortcuts import (
    convert_double_paren_notes_in_blocks,
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


def test_parens_without_flanking_spaces_are_left_alone():
    register, _definitions = _registry()
    runs = [InlineRun(text="voir (a) et (b) ici, pas ((une note)) ici")]

    result = split_double_paren_notes(runs, register)

    # Only the space-flanked "((...))" converts; "(a)"/"(b)" are untouched.
    assert any(r.footnote_ref is not None for r in result)
    assert "(a)" in "".join(r.text for r in result if r.footnote_ref is None)
    assert "(b)" in "".join(r.text for r in result if r.footnote_ref is None)


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
