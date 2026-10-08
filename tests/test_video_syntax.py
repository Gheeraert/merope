"""YouTube URL parsing/normalization and reserved Markdown formatting."""

from __future__ import annotations

import pytest

from bloggen.markdown.video_syntax import (
    DEFAULT_WIDTH,
    MAX_WIDTH,
    MIN_WIDTH,
    ParsedVideoBlock,
    format_video_block,
    is_valid_youtube_id,
    is_valid_width,
    normalize_width,
    parse_video_block,
    parse_video_open_line,
    parse_width_attribute,
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


# --- Width: validation, normalization, serialization, parsing ------------


@pytest.mark.parametrize("width", [MIN_WIDTH, 50, 75, MAX_WIDTH])
def test_is_valid_width_accepts_the_allowed_range(width):
    assert is_valid_width(width) is True


@pytest.mark.parametrize(
    "width",
    [MIN_WIDTH - 1, 24, 0, -1, MAX_WIDTH + 1, 101, "50", "50%", "abc", 75.5, True, False],
)
def test_is_valid_width_rejects_everything_else(width):
    assert is_valid_width(width) is False


def test_normalize_width_none_is_the_default():
    assert normalize_width(None) == DEFAULT_WIDTH


@pytest.mark.parametrize("width", [MIN_WIDTH, 50, 75, MAX_WIDTH])
def test_normalize_width_passes_through_valid_values(width):
    assert normalize_width(width) == width


@pytest.mark.parametrize("width", [24, 101, 0, -1, "75", 75.5, True])
def test_normalize_width_rejects_invalid_values(width):
    with pytest.raises(ValueError):
        normalize_width(width)


def test_parse_width_attribute_absent_is_the_default():
    assert parse_width_attribute(None) == DEFAULT_WIDTH


@pytest.mark.parametrize("raw", ["25", "50", "75", "100"])
def test_parse_width_attribute_accepts_bare_integers_in_range(raw):
    assert parse_width_attribute(raw) == int(raw)


@pytest.mark.parametrize(
    "raw", ["24", "101", "0", "-1", "50%", "abc", "75.5", "", " 50", "50 "]
)
def test_parse_width_attribute_rejects_everything_else(raw):
    with pytest.raises(ValueError):
        parse_width_attribute(raw)


def test_format_video_block_omits_data_width_at_default():
    assert format_video_block(VALID_ID, width=DEFAULT_WIDTH) == format_video_block(VALID_ID)
    assert "data-width" not in format_video_block(VALID_ID, width=100)


def test_format_video_block_writes_data_width_when_not_default():
    rendered = format_video_block(VALID_ID, width=75)
    assert rendered == (
        f':::: {{.merope-video data-provider="youtube" data-video-id="{VALID_ID}" '
        f'data-width="75"}}\n::::'
    )


def test_format_video_block_rejects_invalid_width():
    with pytest.raises(ValueError):
        format_video_block(VALID_ID, width=24)
    with pytest.raises(ValueError):
        format_video_block(VALID_ID, width=101)


def test_parse_video_block_without_width_defaults_to_100():
    block = format_video_block(VALID_ID, "Une légende.")
    assert parse_video_block(block) == ParsedVideoBlock(
        provider="youtube", video_id=VALID_ID, caption="Une légende.", width=100
    )


def test_parse_video_block_with_width_round_trips():
    block = format_video_block(VALID_ID, "Une légende.", width=75)
    assert parse_video_block(block) == ParsedVideoBlock(
        provider="youtube", video_id=VALID_ID, caption="Une légende.", width=75
    )


def test_parse_video_block_without_caption():
    block = format_video_block(VALID_ID, width=50)
    assert parse_video_block(block) == ParsedVideoBlock(
        provider="youtube", video_id=VALID_ID, caption="", width=50
    )


def test_parse_video_block_unescapes_the_caption():
    block = format_video_block(VALID_ID, "*gras* et [lien]")
    parsed = parse_video_block(block)
    assert parsed is not None
    assert parsed.caption == "*gras* et [lien]"


def test_parse_video_block_rejects_invalid_hand_written_width():
    block = (
        f':::: {{.merope-video data-provider="youtube" data-video-id="{VALID_ID}" '
        'data-width="150"}\n::::'
    )
    assert parse_video_block(block) is None


def test_parse_video_block_rejects_non_video_text():
    assert parse_video_block("some\nraw\ntext") is None
    assert parse_video_block(":::: {.merope-encadre}\nTexte.\n::::") is None
