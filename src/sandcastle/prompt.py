"""The prompt resolution pipeline.

Two passes, strict order, matching the original design:

1. `{{KEY}}` substitution — host-side, before the sandbox is touched.
   Applies across the *whole* template, including inside `` !`cmd` ``
   blocks (so `` !`gh issue view {{ISSUE_NUMBER}}` `` works) — this is
   intentional and documented, not a bug to guard against. Each regex
   runs exactly once, so there's no risk of re-processing a shell
   command's stdout as if it were a new substitution target: substitution
   happens first and only once, before any shell command has even run.
2. `` !`command` `` shell-expansion — sandbox-side, after
   `onSandboxReady` hooks have completed, so expansion commands see the
   same repo/dependency state the agent will. All expressions in one
   prompt run concurrently; stdout replaces the expression in-place.
"""

from __future__ import annotations

import concurrent.futures
import re

from sandcastle.errors import PromptError, ShellExpansionError
from sandcastle.protocols.sandbox_provider import SandboxHandle

_KEY_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_SHELL_EXPR_RE = re.compile(r"!`([^`]+)`")

BUILTIN_KEYS = ("SOURCE_BRANCH", "TARGET_BRANCH")

DEFAULT_SHELL_EXPANSION_TIMEOUT_SECONDS = 30.0


def substitute_prompt_args(
    template: str,
    prompt_args: dict[str, str],
    *,
    source_branch: str,
    target_branch: str,
) -> str:
    for builtin in BUILTIN_KEYS:
        if builtin in prompt_args:
            raise PromptError(f"'{builtin}' is a built-in prompt argument and cannot be overridden")

    resolved = {**prompt_args, "SOURCE_BRANCH": source_branch, "TARGET_BRANCH": target_branch}

    referenced: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        referenced.add(key)
        if key not in resolved:
            raise PromptError(f"prompt references undefined key '{{{{{key}}}}}'")
        return resolved[key]

    result = _KEY_RE.sub(_replace, template)

    unused = set(prompt_args) - referenced
    if unused:
        import warnings

        warnings.warn(f"unused prompt_args: {sorted(unused)}", stacklevel=2)

    return result


def expand_shell_expressions(
    template: str,
    sandbox: SandboxHandle,
    *,
    cwd: str | None = None,
    timeout_seconds: float = DEFAULT_SHELL_EXPANSION_TIMEOUT_SECONDS,
) -> str:
    matches = list(_SHELL_EXPR_RE.finditer(template))
    if not matches:
        return template

    def _run(command: str) -> str:
        result = sandbox.exec(command, cwd=cwd, timeout_seconds=timeout_seconds)
        if result.exit_code != 0:
            raise ShellExpansionError(
                f"shell expansion command failed (exit {result.exit_code}): "
                f"{command!r}: {result.stderr.strip()}"
            )
        return result.stdout.rstrip("\n")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(matches), 1)) as pool:
        outputs = list(pool.map(lambda m: _run(m.group(1)), matches))

    # Replace right-to-left so earlier match spans stay valid as we edit.
    result = template
    for match, output in zip(reversed(matches), reversed(outputs)):
        result = result[: match.start()] + output + result[match.end() :]
    return result


def detect_completion_signal(output: str, signals: tuple[str, ...]) -> str | None:
    for signal in signals:
        if signal in output:
            return signal
    return None
