import json

import pytest

from bloggen.config.defaults import build_default_config
from bloggen.config.io import ConfigValidationError, load_config, parse_config, serialize_config


def test_load_valid_json_config():
    loaded = load_config("examples/minimal_project/config/site.json")
    assert loaded.version == "1.0"
    assert loaded.site.title
    assert loaded.site.language == "fr"
    assert loaded.menus.top


def test_invalid_config_raises_clean_error():
    invalid = {
        "site": {"title": "", "language": ""},
        "menus": {"top": {}, "side": "wrong"},
        "paths": {"pages_dir": "", "posts_dir": ""},
    }
    with pytest.raises(ConfigValidationError) as exc:
        parse_config(invalid)
    message = str(exc.value)
    assert "version" in message
    assert "site.title" in message
    assert "menus.top" in message
    assert "menus.side" in message


def test_from_dict_ignores_unknown_keys_in_every_section():
    """A stray/renamed key left over from an older site.json (e.g. after a
    field rename) must be dropped, not raise a raw TypeError out of a
    dataclass constructor — every section of ProjectConfig.from_dict is
    expected to filter unknown keys the same way, not just home/ftp.
    """
    from bloggen.config.models import ProjectConfig

    base = json.loads(serialize_config(build_default_config()))
    for section in (
        "site",
        "banner",
        "paths",
        "content",
        "home",
        "blog",
        "render",
        "media_handling",
        "notes_rendering",
        "footer",
        "build",
        "search",
        "ftp",
    ):
        base.setdefault(section, {})["une_cle_obsolete_inconnue"] = "valeur"

    config = ProjectConfig.from_dict(base)
    assert isinstance(config, ProjectConfig)


def test_default_config_generation():
    config = build_default_config()
    assert config.version == "1.0"
    assert config.paths.pages_dir
    assert len(config.menus.top) >= 1
    assert len(config.menus.side) >= 1


def test_serialization_round_trip_is_stable():
    initial = build_default_config()
    json_first = serialize_config(initial)

    loaded = parse_config(json.loads(json_first))
    json_second = serialize_config(loaded)
    assert json_first == json_second


def test_side_menu_subsection_round_trip():
    from bloggen.config.models import MenuLink, SideMenuSection, SideMenuSubSection

    config = build_default_config()
    config.menus.side.append(
        SideMenuSection(
            label="Rhétorique",
            numbered=True,
            subsections=[
                SideMenuSubSection(
                    label="Bossuet et la rhétorique chrétienne",
                    children=[MenuLink(label="Billet A", target="/billets/a/index.html")],
                )
            ],
        )
    )

    loaded = parse_config(json.loads(serialize_config(config)))
    section = loaded.menus.side[-1]
    assert section.numbered is True
    assert len(section.subsections) == 1
    assert section.subsections[0].label == "Bossuet et la rhétorique chrétienne"
    assert section.subsections[0].children[0].target == "/billets/a/index.html"


def test_side_menu_title_round_trip():
    config = build_default_config()
    config.menus.side_title = "Menu"

    loaded = parse_config(json.loads(serialize_config(config)))
    assert loaded.menus.side_title == "Menu"


def test_side_menu_title_defaults_to_empty_string():
    config = build_default_config()
    assert config.menus.side_title == ""


def test_external_menu_link_with_a_dangerous_scheme_is_rejected():
    """An "external" link is embedded in an <iframe> and an <a href>
    (render_external_link_fragment) — only http(s) belongs there."""
    raw = json.loads(serialize_config(build_default_config()))
    raw["menus"]["top"].append(
        {"label": "Malveillant", "target": "javascript:alert(1)", "target_type": "external", "enabled": True, "new_tab": False}
    )
    with pytest.raises(ConfigValidationError, match="http"):
        parse_config(raw)


def test_external_side_section_with_a_dangerous_scheme_is_rejected():
    raw = json.loads(serialize_config(build_default_config()))
    raw["menus"]["side"].append(
        {
            "label": "Malveillant",
            "target": "javascript:alert(1)",
            "target_type": "external",
            "children": [],
            "subsections": [],
        }
    )
    with pytest.raises(ConfigValidationError, match="http"):
        parse_config(raw)


def test_external_side_subsection_with_a_dangerous_scheme_is_rejected():
    raw = json.loads(serialize_config(build_default_config()))
    raw["menus"]["side"].append(
        {
            "label": "Section",
            "children": [],
            "subsections": [
                {
                    "label": "Malveillant",
                    "target": "javascript:alert(1)",
                    "target_type": "external",
                    "children": [],
                }
            ],
        }
    )
    with pytest.raises(ConfigValidationError, match="http"):
        parse_config(raw)


def test_external_menu_link_with_an_http_url_is_accepted():
    raw = json.loads(serialize_config(build_default_config()))
    raw["menus"]["top"].append(
        {"label": "Wikipédia", "target": "https://fr.wikipedia.org", "target_type": "external", "enabled": True, "new_tab": False}
    )
    config = parse_config(raw)
    assert config.menus.top[-1].target == "https://fr.wikipedia.org"


def test_menu_link_with_an_unknown_target_type_is_rejected():
    raw = json.loads(serialize_config(build_default_config()))
    raw["menus"]["top"].append(
        {"label": "Bogus", "target": "/index.html", "target_type": "bogus", "enabled": True, "new_tab": False}
    )
    with pytest.raises(ConfigValidationError, match="target_type"):
        parse_config(raw)


@pytest.mark.parametrize("bad_url", ["not a url", "ftp://example.org", "example.org", "javascript:alert(1)"])
def test_site_base_url_rejects_non_http_values(bad_url):
    raw = json.loads(serialize_config(build_default_config()))
    raw["site"]["base_url"] = bad_url
    with pytest.raises(ConfigValidationError, match="base_url"):
        parse_config(raw)


def test_site_base_url_accepts_a_real_http_url():
    raw = json.loads(serialize_config(build_default_config()))
    raw["site"]["base_url"] = "https://exemple.org"
    config = parse_config(raw)
    assert config.site.base_url == "https://exemple.org"


def test_site_base_url_empty_string_is_allowed():
    raw = json.loads(serialize_config(build_default_config()))
    raw["site"]["base_url"] = ""
    config = parse_config(raw)
    assert config.site.base_url == ""


def test_ftp_site_url_rejects_non_http_values():
    raw = json.loads(serialize_config(build_default_config()))
    raw["ftp"]["site_url"] = "not a url"
    with pytest.raises(ConfigValidationError, match="site_url"):
        parse_config(raw)


@pytest.mark.parametrize("bad_mode", ["bogus", "recent-posts", "Page"])
def test_home_mode_rejects_unknown_values(bad_mode):
    raw = json.loads(serialize_config(build_default_config()))
    raw["home"]["mode"] = bad_mode
    with pytest.raises(ConfigValidationError, match="home.mode"):
        parse_config(raw)


def test_home_mode_accepts_recent_posts():
    raw = json.loads(serialize_config(build_default_config()))
    raw["home"]["mode"] = "recent_posts"
    config = parse_config(raw)
    assert config.home.mode == "recent_posts"


def test_negative_posts_per_page_is_rejected():
    raw = json.loads(serialize_config(build_default_config()))
    raw["blog"]["posts_per_page"] = -1
    with pytest.raises(ConfigValidationError, match="posts_per_page"):
        parse_config(raw)


def test_non_integer_posts_per_page_is_rejected():
    raw = json.loads(serialize_config(build_default_config()))
    raw["blog"]["posts_per_page"] = "dix"
    with pytest.raises(ConfigValidationError, match="posts_per_page"):
        parse_config(raw)


def test_posts_per_page_of_zero_is_accepted():
    """0 is the documented "no pagination, show everything" value."""
    raw = json.loads(serialize_config(build_default_config()))
    raw["blog"]["posts_per_page"] = 0
    config = parse_config(raw)
    assert config.blog.posts_per_page == 0


@pytest.mark.parametrize("bad_port", [0, -1, 65536, 100000])
def test_ftp_port_out_of_range_is_rejected(bad_port):
    raw = json.loads(serialize_config(build_default_config()))
    raw["ftp"]["port"] = bad_port
    with pytest.raises(ConfigValidationError, match="ftp.port"):
        parse_config(raw)


def test_ftp_port_in_range_is_accepted():
    raw = json.loads(serialize_config(build_default_config()))
    raw["ftp"]["port"] = 2121
    config = parse_config(raw)
    assert config.ftp.port == 2121


def test_two_path_fields_pointing_at_the_same_folder_are_rejected():
    """A collision means one role silently overwrites/reads the other
    (e.g. output_dir == assets_dir would wipe assets on every clean)."""
    raw = json.loads(serialize_config(build_default_config()))
    raw["paths"]["output_dir"] = raw["paths"]["assets_dir"]
    with pytest.raises(ConfigValidationError, match="output_dir"):
        parse_config(raw)


def test_path_fields_with_different_separators_still_collide():
    raw = json.loads(serialize_config(build_default_config()))
    raw["paths"]["output_dir"] = "assets/"
    raw["paths"]["assets_dir"] = "assets"
    with pytest.raises(ConfigValidationError, match="output_dir"):
        parse_config(raw)


def test_nested_paths_like_the_defaults_do_not_collide():
    """theme/templates and theme/xslt both live under theme_dir by
    default — nesting is fine, only exact equality is a collision."""
    config = build_default_config()
    assert config.paths.templates_dir.startswith(config.paths.theme_dir)
    assert config.paths.xslt_dir.startswith(config.paths.theme_dir)
    # No exception: the default config itself must validate cleanly.
    parse_config(json.loads(serialize_config(config)))
