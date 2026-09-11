from __future__ import annotations

import json

import pytest

from bloggen.ui.qt_editor_protocol import (
    PROTOCOL_VERSION,
    ProtocolCommand,
    ProtocolError,
    ProtocolEvent,
    encode_command,
    parse_command_line,
    parse_event_line,
)


def test_config_requested_event_is_strictly_parsed():
    event = parse_event_line(
        '{"protocol":1,"type":"config_requested","request_id":12}'
    )

    assert event == ProtocolEvent(
        protocol=PROTOCOL_VERSION,
        type="config_requested",
        request_id=12,
    )


@pytest.mark.parametrize(
    "line",
    [
        '{"protocol":1,"type":"config_requested"}',
        '{"protocol":1,"type":"config_requested","request_id":true}',
        '{"protocol":1,"type":"config_requested","request_id":0}',
        '{"protocol":1,"type":"config_requested","request_id":-2}',
        '{"protocol":1,"type":"ready","request_id":1}',
    ],
)
def test_invalid_config_requested_event_is_rejected(line):
    with pytest.raises(ProtocolError):
        parse_event_line(line)


def test_config_snapshot_command_encode_parse_round_trip():
    command = ProtocolCommand(
        protocol=PROTOCOL_VERSION,
        type="config_snapshot",
        request_id=3,
        config={"site": {"title": "Nouveau"}},
    )

    assert parse_command_line(encode_command(command)) == command


def test_config_error_command_encode_parse_round_trip():
    command = ProtocolCommand(
        protocol=PROTOCOL_VERSION,
        type="config_error",
        request_id=4,
        message="Configuration invalide",
    )

    assert parse_command_line(encode_command(command)) == command


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"protocol": 2, "type": "config_error", "request_id": 1, "message": "x"},
        {"protocol": 1, "type": "unknown", "request_id": 1},
        {"protocol": 1, "type": "config_snapshot", "request_id": 1, "config": []},
        {"protocol": 1, "type": "config_error", "request_id": 1},
        {
            "protocol": 1,
            "type": "config_error",
            "request_id": 1,
            "message": "x",
            "extra": True,
        },
        {"protocol": 1, "type": "config_error", "request_id": True, "message": "x"},
    ],
)
def test_invalid_parent_command_is_rejected(payload):
    with pytest.raises(ProtocolError):
        parse_command_line(json.dumps(payload))


@pytest.mark.parametrize(
    "line",
    [
        '{"protocol":1,"type":"ready"}',
        '{"protocol":1,"type":"opened","path":"C:/article.md"}',
        '{"protocol":1,"type":"saved","path":"C:/article.md"}',
        '{"protocol":1,"type":"open_refused","path":"C:/article.md","message":"x"}',
        '{"protocol":1,"type":"error","message":"x"}',
        '{"protocol":1,"type":"closed"}',
    ],
)
def test_historical_events_remain_accepted(line):
    assert parse_event_line(line).type
