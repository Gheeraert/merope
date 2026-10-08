"""YouTube URL parsing/normalization and reserved Markdown formatting."""

from __future__ import annotations

import pytest

from bloggen.markdown.video_syntax import (
    format_video_block,
    is_valid_youtube_id,
    parse_video_open_line,
    parse_youtube_url,
    youtube_watch_url,
)

VALID_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VALID_ID}",
        f"https://youtube.com/watch?v={VALID_ID}",
        f"http://www.youtube.com/watch?v={VALID_ID}",
        f"https://youtu.be/{VALID_ID}",
        f"https://www.youtube.com/embed/{VALID_ID}",
        f"https://www.youtube.com/shorts/{VALID_ID}",
        f"https://www.youtube.com/watch?v={VALID_ID}&t=42s",
        f"https://youtu.be/{VALID_ID}?si=abc123",
        f"https://www.youtube.com/watch?list=PL123&v={VALID_ID}",
    ],
)
def test_valid_urls_extract_the_canonical_id(url):
    assert parse_youtube_url(url) == VALID_ID


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url at all",
        "https://www.youtube.evil.com/watch?v=" + VALID_ID,
        "https://notyoutube.com/watch?v=" + VALID_ID,
        "https://youtubevideos.com/watch?v=" + VALID_ID,
        "https://vimeo.com/123456789",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://youtube.com/watch?v=" + VALID_ID,
        "https://www.youtube.com/watch?v=",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=" + VALID_ID + "x",
        "https://www.youtube.com/watch?v=has space12",
        "https://youtu.be/",
        "https://youtu.be/" + VALID_ID + "/extra",
        "https://www.youtube.com/embed/",
        "https://www.youtube.com/playlist?list=PL123",
        "https://www.youtube.com/",
    ],
)
def test_invalid_or_unrecognized_urls_are_rejected(url):
    assert parse_youtube_url(url) is None


def test_is_valid_youtube_id():
    assert is_valid_youtube_id(VALID_ID) is True
    assert is_valid_youtube_id("too-short") is False
    assert is_valid_youtube_id(VALID_ID + "x") is False
    assert is_valid_youtube_id("has space!!") is False


def test_youtube_watch_url_is_built_only_from_the_id():
    assert youtube_watch_url(VALID_ID) == f"https://www.youtube.com/watch?v={VALID_ID}"


def test_format_video_block_without_caption():
    assert format_video_block(VALID_ID) == (
        f':::: {{.merope-video data-provider="youtube" data-video-id="{VALID_ID}"}}\n::::'
    )


def test_format_video_block_with_caption():
    assert format_video_block(VALID_ID, "Une légende.") == (
        f':::: {{.merope-video data-provider="youtube" data-video-id="{VALID_ID}"}}\n'
        "Une légende\\.\n::::"
    )


def test_format_video_block_escapes_markdown_in_caption():
    rendered = format_video_block(VALID_ID, "*gras* et [lien]")
    assert "\\*gras\\* et \\[lien\\]" in rendered


def test_format_video_block_rejects_invalid_id():
    with pytest.raises(ValueError):
        format_video_block("not-an-id")


def test_format_video_block_rejects_unsupported_provider():
    with pytest.raises(ValueError):
        format_video_block(VALID_ID, provider="vimeo")


def test_parse_video_open_line_recognizes_the_shape():
    line = f':::: {{.merope-video data-provider="youtube" data-video-id="{VALID_ID}"}}'
    assert parse_video_open_line(line) == ("youtube", VALID_ID)
    assert parse_video_open_line(":::: {.merope-encadre}") is None
    assert parse_video_open_line("not a fence at all") is None
