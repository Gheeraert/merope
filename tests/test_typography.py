from bloggen.markdown.rich_text_model import InlineRun
from bloggen.markdown.typography import (
    CLOSING_GUILLEMET,
    NBSP,
    OPENING_GUILLEMET,
    apply_french_typography,
    convert_curly_quotes_to_guillemets,
    convert_straight_quotes_stateful,
    fix_guillemet_spacing,
    fix_page_number_spacing,
    is_valid_century_ordinal,
    split_century_ordinals,
)

_CURLY_OPEN = "“"
_CURLY_CLOSE = "”"


def test_straight_quotes_become_alternating_guillemets():
    result = apply_french_typography('Il a dit "bonjour" hier.')
    assert result == f"Il a dit «{NBSP}bonjour{NBSP}» hier."


def test_nested_quote_pairs_alternate_correctly():
    result = apply_french_typography('"Un" texte "deux" fois.')
    assert result == f"«{NBSP}Un{NBSP}» texte «{NBSP}deux{NBSP}» fois."


def test_double_punctuation_glued_gets_nbsp():
    assert apply_french_typography("Vraiment!") == f"Vraiment{NBSP}!"
    assert apply_french_typography("Alors?") == f"Alors{NBSP}?"
    assert apply_french_typography("Attention:") == f"Attention{NBSP}:"
    assert apply_french_typography("Salut;") == f"Salut{NBSP};"


def test_double_punctuation_with_regular_space_gets_fixed():
    assert apply_french_typography("Vraiment !") == f"Vraiment{NBSP}!"


def test_double_punctuation_already_nbsp_is_unchanged():
    text = f"Vraiment{NBSP}!"
    assert apply_french_typography(text) == text


def test_is_idempotent():
    text = '"Vraiment ?" a-t-il demandé !'
    once = apply_french_typography(text)
    twice = apply_french_typography(once)
    assert once == twice


def test_combined_realistic_sentence():
    result = apply_french_typography('"Vraiment ?" a-t-il demandé !')
    assert result == f"«{NBSP}Vraiment{NBSP}?{NBSP}» a-t-il demandé{NBSP}!"


def test_curly_quotes_are_mapped_directly_to_guillemets():
    text = f"Il a dit {_CURLY_OPEN}bonjour{_CURLY_CLOSE} hier."
    result = convert_curly_quotes_to_guillemets(text)
    assert result == f"Il a dit {OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET} hier."


def test_apply_french_typography_also_handles_curly_quotes():
    text = f"Il a dit {_CURLY_OPEN}bonjour{_CURLY_CLOSE} hier!"
    result = apply_french_typography(text)
    assert result == f"Il a dit {OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET} hier{NBSP}!"


def test_stateful_quote_conversion_threads_parity_across_calls():
    text1, parity = convert_straight_quotes_stateful("Un ", opening_next=True)
    text2, parity = convert_straight_quotes_stateful('"debut', opening_next=parity)
    text3, parity = convert_straight_quotes_stateful(' et fin"', opening_next=parity)
    assert text1 + text2 + text3 == f"Un {OPENING_GUILLEMET}{NBSP}debut et fin{NBSP}{CLOSING_GUILLEMET}"
    assert parity is True


def test_stateful_quote_conversion_matches_default_when_starting_fresh():
    text, _ = convert_straight_quotes_stateful('"Vraiment ?"')
    assert text == f"{OPENING_GUILLEMET}{NBSP}Vraiment ?{NBSP}{CLOSING_GUILLEMET}"


def test_is_valid_century_ordinal():
    assert is_valid_century_ordinal("I", "er") is True
    assert is_valid_century_ordinal("I", "e") is False
    assert is_valid_century_ordinal("II", "e") is True
    assert is_valid_century_ordinal("XXI", "e") is True
    assert is_valid_century_ordinal("II", "er") is False


def test_split_century_ordinals_basic():
    runs = split_century_ordinals([InlineRun(text="Au XXIe siecle, tout change.")])
    assert [(r.text, r.superscript) for r in runs] == [
        ("Au XXI", False),
        ("e", True),
        (" siecle, tout change.", False),
    ]


def test_split_century_ordinals_first_century_uses_er():
    runs = split_century_ordinals([InlineRun(text="Le Ier siecle.")])
    assert [(r.text, r.superscript) for r in runs] == [
        ("Le I", False),
        ("er", True),
        (" siecle.", False),
    ]


def test_split_century_ordinals_multiple_occurrences_in_one_run():
    runs = split_century_ordinals([InlineRun(text="Du Ier siecle au XXIe siecle.")])
    assert [(r.text, r.superscript) for r in runs] == [
        ("Du I", False),
        ("er", True),
        (" siecle au XXI", False),
        ("e", True),
        (" siecle.", False),
    ]


def test_split_century_ordinals_rejects_invalid_combination():
    runs = split_century_ordinals([InlineRun(text="IIer siecle")])
    assert [(r.text, r.superscript) for r in runs] == [("IIer siecle", False)]


def test_split_century_ordinals_preserves_other_flags():
    runs = split_century_ordinals([InlineRun(text="XXIe siecle", bold=True, italic=True)])
    assert [(r.text, r.bold, r.italic, r.superscript) for r in runs] == [
        ("XXI", True, True, False),
        ("e", True, True, True),
        (" siecle", True, True, False),
    ]


def test_split_century_ordinals_leaves_images_and_footnotes_untouched():
    image_run = InlineRun(image_src="a.jpg", image_alt="Alt")
    footnote_run = InlineRun(footnote_ref="1")
    runs = split_century_ordinals([image_run, footnote_run])
    assert runs == [image_run, footnote_run]


def test_split_century_ordinals_is_idempotent():
    once = split_century_ordinals([InlineRun(text="Au XXIe siecle.")])
    twice = split_century_ordinals(once)
    assert [(r.text, r.superscript) for r in once] == [(r.text, r.superscript) for r in twice]


def test_fix_page_number_spacing_single_page():
    assert fix_page_number_spacing("Voir p. 12.") == f"Voir p.{NBSP}12."


def test_fix_page_number_spacing_plural_abbreviation():
    assert fix_page_number_spacing("Cf. pp. 12-15.") == f"Cf. pp.{NBSP}12-15."


def test_fix_page_number_spacing_already_nbsp_is_unchanged():
    text = f"Voir p.{NBSP}12."
    assert fix_page_number_spacing(text) == text


def test_fix_page_number_spacing_ignores_non_digit_followers():
    text = "Il y a p. ex. autre chose."
    assert fix_page_number_spacing(text) == text


def test_fix_page_number_spacing_ignores_p_glued_inside_a_word():
    text = "app. 12 ne doit pas changer."
    assert fix_page_number_spacing(text) == text


def test_fix_page_number_spacing_multiple_occurrences():
    text = "Voir p. 12 et p. 34."
    assert fix_page_number_spacing(text) == f"Voir p.{NBSP}12 et p.{NBSP}34."


def test_apply_french_typography_also_fixes_page_number_spacing():
    result = apply_french_typography("Voir p. 12.")
    assert result == f"Voir p.{NBSP}12."


def test_fix_guillemet_spacing_converts_regular_space_after_opening():
    text = f"{OPENING_GUILLEMET} bonjour{NBSP}{CLOSING_GUILLEMET}"
    assert fix_guillemet_spacing(text) == f"{OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET}"


def test_fix_guillemet_spacing_converts_regular_space_before_closing():
    text = f"{OPENING_GUILLEMET}{NBSP}bonjour {CLOSING_GUILLEMET}"
    assert fix_guillemet_spacing(text) == f"{OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET}"


def test_fix_guillemet_spacing_converts_both_sides_at_once():
    text = f"Il a dit {OPENING_GUILLEMET} bonjour {CLOSING_GUILLEMET} hier."
    assert fix_guillemet_spacing(text) == (
        f"Il a dit {OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET} hier."
    )


def test_fix_guillemet_spacing_leaves_existing_nbsp_untouched():
    text = f"{OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET}"
    assert fix_guillemet_spacing(text) == text


def test_fix_guillemet_spacing_does_not_insert_a_space_when_glued():
    text = f"{OPENING_GUILLEMET}bonjour{CLOSING_GUILLEMET}"
    assert fix_guillemet_spacing(text) == text


def test_fix_guillemet_spacing_is_idempotent():
    once = fix_guillemet_spacing(f"{OPENING_GUILLEMET} bonjour {CLOSING_GUILLEMET}")
    twice = fix_guillemet_spacing(once)
    assert once == twice


def test_apply_french_typography_fixes_pre_existing_guillemets_too():
    text = f"Il a dit {OPENING_GUILLEMET} bonjour {CLOSING_GUILLEMET} hier."
    result = apply_french_typography(text)
    assert result == f"Il a dit {OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET} hier."
    # The chevrons themselves must not be duplicated/re-paired.
    assert result.count(OPENING_GUILLEMET) == 1
    assert result.count(CLOSING_GUILLEMET) == 1
