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
