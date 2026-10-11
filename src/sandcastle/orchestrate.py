"""The per-run iteration loop.

Each iteration is a brand-new agent process with no conversational memory
of the previous one — only the repo/worktree state persists between
iterations. That's why shell-expansion re-runs fresh every iteration: the
`` !`ls issues/open/*.md` `` style blocks need to see whatever the previous
iteration just committed.
"""

from __future__ import annotations

from sandcastle.log import RunLogger
from sandcastle.prompt import detect_completion_signal, expand_shell_expressions
from sandcastle.protocols.agent_provider import AgentCommandOptions, AgentProvider
from sandcastle.protocols.sandbox_provider import SandboxHandle
from sandcastle.types import IterationResult


def run_iterations(
    *,
    sandbox: SandboxHandle,
    agent: AgentProvider,
    substituted_template: str,
    sandbox_cwd: str,
    max_iterations: int,
    completion_signals: tuple[str, ...],
    shell_expansion_timeout_seconds: float,
    logger: RunLogger,
    name: str,
) -> tuple[list[IterationResult], str | None]:
    iterations: list[IterationResult] = []
    matched_signal: str | None = None

    for i in range(1, max_iterations + 1):
        logger.line(f"[{name}] iteration {i}/{max_iterations}: expanding shell expressions")
        resolved_prompt = expand_shell_expressions(
            substituted_template,
            sandbox,
            cwd=sandbox_cwd,
            timeout_seconds=shell_expansion_timeout_seconds,
        )

        print_command = agent.build_print_command(AgentCommandOptions(prompt=resolved_prompt))

        raw_lines: list[str] = []

        def _on_line(line: str, _raw_lines: list[str] = raw_lines) -> None:
            _raw_lines.append(line)
            for event in agent.parse_stream_line(line):
                logger.line(f"[{name}] {event!r}")

        logger.line(f"[{name}] iteration {i}/{max_iterations}: agent started")
        result = sandbox.exec(
            print_command.command,
            cwd=sandbox_cwd,
            stdin=print_command.stdin,
            on_line=_on_line,
        )

        raw_output = "\n".join(raw_lines) if raw_lines else result.stdout

        session_id: str | None = None
        for line in raw_output.splitlines():
            for event in agent.parse_stream_line(line):
                if getattr(event, "session_id", None):
                    session_id = event.session_id  # type: ignore[attr-defined]

        matched_signal = detect_completion_signal(raw_output, completion_signals)
        iterations.append(
            IterationResult(
                raw_output=raw_output,
                completion_signal=matched_signal,
                session_id=session_id,
            )
        )
        logger.line(f"[{name}] iteration {i}/{max_iterations}: agent finished (exit {result.exit_code})")

        if matched_signal:
            logger.line(f"[{name}] completion signal '{matched_signal}' detected — stopping early")
            break

    return iterations, matched_signal
