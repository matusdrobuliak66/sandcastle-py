"""Shared data types used across sandcastle's protocols and implementations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True)
class Mount:
    host_path: str
    sandbox_path: str
    readonly: bool = False


@dataclass(frozen=True)
class Commit:
    sha: str


@dataclass(frozen=True)
class HookSpec:
    command: str
    sudo: bool = False
    timeout_seconds: float = 120.0


@dataclass(frozen=True)
class SandboxHooks:
    """Lifecycle hooks, grouped by where they run."""

    host_on_worktree_ready: tuple[HookSpec, ...] = ()
    host_on_sandbox_ready: tuple[HookSpec, ...] = ()
    sandbox_on_sandbox_ready: tuple[HookSpec, ...] = ()


@dataclass(frozen=True)
class Timeouts:
    copy_to_worktree_seconds: float = 60.0
    git_setup_seconds: float = 10.0
    commit_collection_seconds: float = 30.0
    shell_expansion_seconds: float = 30.0
    idle_seconds: float = 600.0
    completion_seconds: float = 60.0


@dataclass(frozen=True)
class IterationResult:
    """Result of a single agent process invocation."""

    raw_output: str
    completion_signal: str | None
    session_id: str | None = None


@dataclass(frozen=True)
class RunResult:
    """Result of a `Sandbox.run()` call (one or more iterations)."""

    name: str
    branch: str
    commits: tuple[Commit, ...]
    iterations: tuple[IterationResult, ...]
    completion_signal: str | None


LogCallback = Callable[[str], None]
