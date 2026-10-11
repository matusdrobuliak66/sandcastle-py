"""The AgentProvider protocol.

An AgentProvider adapts a specific coding-agent CLI (only `pi` ships in v1)
to a common shape: build the shell command to invoke it, and parse its
stdout lines into a normalized event stream. Sandcastle itself never knows
anything about what a given CLI's output looks like beyond this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AgentCommandOptions:
    prompt: str


@dataclass(frozen=True)
class PrintCommand:
    """A command to run inside the sandbox, with its stdin payload."""

    command: str
    stdin: str | None = None


@dataclass(frozen=True)
class TextEvent:
    text: str


@dataclass(frozen=True)
class ToolCallEvent:
    name: str
    args: dict


@dataclass(frozen=True)
class ResultEvent:
    tool_name: str
    result_text: str
    is_error: bool


@dataclass(frozen=True)
class SessionIdEvent:
    session_id: str


ParsedStreamEvent = TextEvent | ToolCallEvent | ResultEvent | SessionIdEvent


class AgentProvider(Protocol):
    name: str
    env: dict[str, str]

    def build_print_command(self, options: AgentCommandOptions) -> PrintCommand: ...

    def parse_stream_line(self, line: str) -> list[ParsedStreamEvent]: ...
