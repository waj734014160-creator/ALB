# coding: utf-8
"""Small parsing helpers shared by ALB remote tools."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any


def extract_json(text: str) -> Any:
    start = text.find("{")
    array_start = text.find("[")
    if array_start >= 0 and (start < 0 or array_start < start):
        start = array_start
    if start < 0:
        raise ValueError("Remote output did not contain JSON")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text[start:])
    return obj


def parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    value = text.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    value = re.sub(r"(\.\d{6})\d+([+-]\d\d:\d\d)$", r"\1\2", value)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
