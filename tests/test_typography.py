from bloggen.markdown.typography import NBSP, apply_french_typography


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
