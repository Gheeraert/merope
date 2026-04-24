from bloggen.content.slugify import ensure_unique_slug, slugify


def test_slugify_ascii_stable():
    assert slugify("Élément de Test") == "element-de-test"


def test_slugify_fallback_for_empty():
    assert slugify("***") == "untitled"


def test_ensure_unique_slug_appends_counter():
    used: set[str] = set()
    assert ensure_unique_slug("page", used) == "page"
    assert ensure_unique_slug("page", used) == "page-2"
    assert ensure_unique_slug("page", used) == "page-3"
