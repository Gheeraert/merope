from bloggen.markdown.image_attributes import (
    format_image_attributes,
    parse_image_attributes,
    strip_image_attributes,
)


def test_parse_image_attributes():
    assert parse_image_attributes("width=300 height=200 align=left") == {
        "width": "300",
        "height": "200",
        "align": "left",
    }


def test_parse_image_attributes_ignores_malformed_tokens():
    assert parse_image_attributes("width=300 garbage align=") == {"width": "300"}


def test_format_image_attributes_roundtrip():
    attrs = {"width": "300", "height": "200", "align": "left"}
    formatted = format_image_attributes(attrs)
    assert formatted == "{width=300 height=200 align=left}"
    assert parse_image_attributes(formatted.strip("{}")) == attrs


def test_format_image_attributes_empty_returns_empty_string():
    assert format_image_attributes({}) == ""
    assert format_image_attributes({"width": ""}) == ""


def test_strip_image_attributes_removes_suffix_and_collects_mapping():
    text = "Voir ![Alt](assets/images/x.jpg){width=300 height=200} et texte."
    cleaned, mapping = strip_image_attributes(text)
    assert cleaned == "Voir ![Alt](assets/images/x.jpg) et texte."
    assert mapping == {"assets/images/x.jpg": {"width": "300", "height": "200"}}


def test_strip_image_attributes_leaves_plain_images_untouched():
    text = "![Alt](assets/images/x.jpg)"
    cleaned, mapping = strip_image_attributes(text)
    assert cleaned == text
    assert mapping == {}


def test_strip_image_attributes_multiple_images():
    text = "![A](a.jpg){width=100} et ![B](b.jpg){align=right}"
    cleaned, mapping = strip_image_attributes(text)
    assert cleaned == "![A](a.jpg) et ![B](b.jpg)"
    assert mapping == {"a.jpg": {"width": "100"}, "b.jpg": {"align": "right"}}
