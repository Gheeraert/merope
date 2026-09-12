from bloggen.markdown.rich_text_model import InlineRun


def test_inline_run_preserves_historical_positional_field_order():
    run = InlineRun("texte", False, False, True)

    assert run.strikethrough is True
    assert run.underline is False
