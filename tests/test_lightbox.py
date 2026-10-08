from __future__ import annotations

from lxml import html as lxml_html

from bloggen.render.lightbox import apply_lightbox_markup


def _fragment_with_video_and_trailing_text() -> str:
    return (
        "<article>"
        '<figure class="video-embed">'
        '<div class="video-embed-frame">'
        '<iframe src="https://www.youtube-nocookie.com/embed/test"></iframe>'
        "</div>"
        "</figure>"
        "<p>Texte après</p>"
        "</article>"
    )


def test_apply_lightbox_markup_never_self_closes_iframe():
    result = apply_lightbox_markup(
        _fragment_with_video_and_trailing_text(),
        enabled=True,
        group_name="essai",
        use_caption=False,
    )

    assert "</iframe>" in result.html_fragment
    assert "/>" not in result.html_fragment


def test_apply_lightbox_markup_keeps_trailing_text_outside_the_iframe():
    result = apply_lightbox_markup(
        _fragment_with_video_and_trailing_text(),
        enabled=True,
        group_name="essai",
        use_caption=False,
    )

    document = lxml_html.fromstring(f"<div>{result.html_fragment}</div>")
    iframes = document.xpath("//iframe")
    assert len(iframes) == 1

    paragraphs = document.xpath("//p[text()='Texte après']")
    assert len(paragraphs) == 1
    assert paragraphs[0].xpath("ancestor::iframe") == []
