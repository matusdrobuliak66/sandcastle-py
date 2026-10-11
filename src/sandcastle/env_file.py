"""A tiny hand-rolled `.env` parser.

No `python-dotenv` dependency — the JS sandcastle doesn't pull in `dotenv`
either, there's direct precedent for hand-rolling this. Supports
`KEY=VALUE`, `#` comments, blank lines, and optional single/double quotes
around the value.
"""

from __future__ import annotations

import os


def parse_env_file(path: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not os.path.exists(path):
        return result
    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            result[key] = value
    return result
