"""JSON-форматтер логов."""

from __future__ import annotations

import json
import logging

from config.logging import JsonFormatter


def test_json_formatter_emits_parseable_json_with_extras():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "привет %s", ("мир",), None)
    record.request_id = "abc-123"

    data = json.loads(JsonFormatter().format(record))

    assert data["msg"] == "привет мир"
    assert data["level"] == "INFO"
    assert data["logger"] == "t"
    assert data["request_id"] == "abc-123"
    assert data["ts"]
