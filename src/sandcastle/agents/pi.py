"""The `pi` agent provider.

Prompt delivery: empirically, `pi -p --mode json ... @file` hangs (it seems
to wait for an explicit positional message in addition to the `@file`
attachment). Piping the prompt via stdin works and is what the JS
sandcastle's `pi` provider does too (`stdin: prompt`), so that's what this
provider does.

`parse_stream_line` is built directly against real `--mode json` output
captured from a live run against the vLLM endpoint (see PLAN.md's
"Empirical findings"), not guessed from documentation.
"""

from __future__ import annotations

import json
import shlex

from sandcastle.protocols.agent_provider import (
    AgentCommandOptions,
    ParsedStreamEvent,
    PrintCommand,
    ResultEvent,
    SessionIdEvent,
    TextEvent,
    ToolCallEvent,
)


class PiAgentProvider:
    name = "pi"

    def __init__(
        self,
        model: str,
        *,
        thinking: str | None = None,
        tools: list[str] | None = None,
        no_tools: bool = False,
        no_builtin_tools: bool = False,
        env: dict[str, str] | None = None,
    ) -> None:
        if tools and (no_tools or no_builtin_tools):
            raise ValueError("tools is mutually exclusive with no_tools/no_builtin_tools")
        self.model = model
        self.thinking = thinking
        self.tools = tools
        self.no_tools = no_tools
        self.no_builtin_tools = no_builtin_tools
        self.env = dict(env or {})

    def build_print_command(self, options: AgentCommandOptions) -> PrintCommand:
        parts = ["pi", "-p", "--mode", "json", "--model", shlex.quote(self.model)]
        if self.thinking:
            parts += ["--thinking", shlex.quote(self.thinking)]
        if self.no_tools:
            parts.append("--no-tools")
        elif self.no_builtin_tools:
            parts.append("--no-builtin-tools")
        if self.tools:
            parts += ["--tools", shlex.quote(",".join(self.tools))]
        return PrintCommand(command=" ".join(parts), stdin=options.prompt)

    def parse_stream_line(self, line: str) -> list[ParsedStreamEvent]:
        line = line.strip()
        if not line:
            return []
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return []

        event_type = event.get("type")

        if event_type == "session":
            session_id = event.get("id")
            if isinstance(session_id, str):
                return [SessionIdEvent(session_id=session_id)]
            return []

        if event_type == "message_update":
            assistant_event = event.get("assistantMessageEvent") or {}
            if assistant_event.get("type") == "text_delta":
                delta = assistant_event.get("delta")
                if isinstance(delta, str) and delta:
                    return [TextEvent(text=delta)]
            return []

        if event_type == "tool_execution_start":
            return [
                ToolCallEvent(
                    name=event.get("toolName", ""),
                    args=event.get("args") or {},
                )
            ]

        if event_type == "tool_execution_end":
            result = event.get("result") or {}
            content = result.get("content") or []
            text = "".join(
                item.get("text", "") for item in content if item.get("type") == "text"
            )
            return [
                ResultEvent(
                    tool_name=event.get("toolName", ""),
                    result_text=text,
                    is_error=bool(event.get("isError", False)),
                )
            ]

        # Everything else (agent_start, turn_start, message_start/end,
        # thinking_*, toolcall_* streaming deltas, turn_end, agent_end) is
        # intentionally ignored — unknown/uninteresting types are tolerated,
        # never fatal, matching the JS providers' tolerance of unrecognized
        # event shapes.
        return []
