from bloggen.config.models import MenuLink, SideMenuSection
from bloggen.ui.menu_editor import (
    add_side_child,
    add_side_section,
    add_top_menu_item,
    move_side_child_up,
    move_side_section_down,
    move_top_menu_item_up,
    remove_side_child,
    remove_top_menu_item,
    toggle_side_child,
    toggle_top_menu_item,
)


def test_top_menu_basic_manipulation():
    items: list[MenuLink] = []
    add_top_menu_item(items, MenuLink(label="Accueil", target="/index.html"))
    add_top_menu_item(items, MenuLink(label="Blog", target="/blog/index.html"))

    assert [item.label for item in items] == ["Accueil", "Blog"]

    move_top_menu_item_up(items, 1)
    assert [item.label for item in items] == ["Blog", "Accueil"]

    toggle_top_menu_item(items, 0)
    assert items[0].enabled is False

    removed = remove_top_menu_item(items, 1)
    assert removed.label == "Accueil"
    assert len(items) == 1


def test_side_menu_basic_manipulation():
    sections: list[SideMenuSection] = []
    first = SideMenuSection(label="Section A")
    second = SideMenuSection(label="Section B")
    add_side_section(sections, first)
    add_side_section(sections, second)

    assert [section.label for section in sections] == ["Section A", "Section B"]
    move_side_section_down(sections, 0)
    assert [section.label for section in sections] == ["Section B", "Section A"]

    section = sections[0]
    add_side_child(section, MenuLink(label="Sous 1", target="/sous-1"))
    add_side_child(section, MenuLink(label="Sous 2", target="/sous-2"))
    move_side_child_up(section, 1)
    assert [child.label for child in section.children] == ["Sous 2", "Sous 1"]

    toggle_side_child(section, 0)
    assert section.children[0].enabled is False

    removed = remove_side_child(section, 1)
    assert removed.label == "Sous 1"
