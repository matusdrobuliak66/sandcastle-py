"""Minimal run logging: write lines to a file and/or print them."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RunLogger:
    path: str | None = None
    echo: bool = True

    def __post_init__(self) -> None:
        if self.path:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    def line(self, text: str) -> None:
        if self.echo:
            print(text)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
