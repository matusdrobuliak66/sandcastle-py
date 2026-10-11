"""Lifecycle hooks: shell commands run at specific points in sandbox setup.

v1 simplification: hooks run sequentially (host hooks, then sandbox hooks),
not concurrently as the original does. For the handful of setup commands
these templates actually use (`npm install`, copying a config file) the
time difference is negligible, and sequential execution is much easier to
reason about when something fails.
"""

from __future__ import annotations

import subprocess

from sandcastle.errors import HookError, HookTimeoutError
from sandcastle.protocols.sandbox_provider import SandboxHandle
from sandcastle.types import HookSpec


def run_host_hooks(hooks: tuple[HookSpec, ...], *, cwd: str) -> None:
    for hook in hooks:
        try:
            subprocess.run(
                hook.command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=hook.timeout_seconds,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise HookTimeoutError(f"host hook timed out: {hook.command!r}") from exc
        except subprocess.CalledProcessError as exc:
            raise HookError(
                f"host hook failed (exit {exc.returncode}): {hook.command!r}: {exc.stderr}"
            ) from exc


def run_sandbox_hooks(hooks: tuple[HookSpec, ...], handle: SandboxHandle) -> None:
    for hook in hooks:
        try:
            result = handle.exec(hook.command, sudo=hook.sudo, timeout_seconds=hook.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise HookTimeoutError(f"sandbox hook timed out: {hook.command!r}") from exc
        if result.exit_code != 0:
            raise HookError(
                f"sandbox hook failed (exit {result.exit_code}): {hook.command!r}: {result.stderr}"
            )
