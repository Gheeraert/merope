"""Lightbox enhancement hooks for rendered HTML fragments."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree, html


@dataclass(slots=True)
class LightboxRenderResult:
    html_fragment: str
    enhanced_images: int


def apply_lightbox_markup(
    html_fragment: str,
    *,
    enabled: bool,
    group_name: str,
    use_caption: bool,
) -> LightboxRenderResult:
    root = html.fragment_fromstring(html_fragment, create_parent="div")
    links = root.xpath(
        ".//figure[contains(concat(' ', normalize-space(@class), ' '), ' article-figure ')]"
        "//a[contains(concat(' ', normalize-space(@class), ' '), ' figure-image-link ')]"
    )

    enhanced = 0
    for index, link in enumerate(links, start=1):
        if enabled:
            _add_class(link, "lightbox-link")
            link.set("data-lightbox-group", group_name)
            link.set("data-lightbox-index", str(index))
            caption = _resolve_caption(link) if use_caption else ""
            if caption:
                link.set("data-lightbox-caption", caption)
            link.set("aria-haspopup", "dialog")
            enhanced += 1
        else:
            _remove_class(link, "lightbox-link")
            for key in (
                "data-lightbox-group",
                "data-lightbox-index",
                "data-lightbox-caption",
                "aria-haspopup",
            ):
                link.attrib.pop(key, None)

    return LightboxRenderResult(
        html_fragment="".join(etree.tostring(child, encoding="unicode") for child in root),
        enhanced_images=enhanced,
    )


def _resolve_caption(link: etree._Element) -> str:
    figure = link.getparent()
    while figure is not None and figure.tag.lower() != "figure":
        figure = figure.getparent()
    if figure is None:
        return ""

    captions = figure.xpath("./figcaption")
    if not captions:
        return ""

    return " ".join(captions[0].text_content().split())


def _add_class(element: etree._Element, class_name: str) -> None:
    classes = element.get("class", "").split()
    if class_name in classes:
        return
    classes.append(class_name)
    element.set("class", " ".join(classes).strip())


def _remove_class(element: etree._Element, class_name: str) -> None:
    classes = [value for value in element.get("class", "").split() if value != class_name]
    if classes:
        element.set("class", " ".join(classes))
        return
    element.attrib.pop("class", None)
