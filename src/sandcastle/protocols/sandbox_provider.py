"""The SandboxProvider / SandboxHandle protocols.

A SandboxProvider knows how to create an isolated place to exec commands
(only Docker ships in v1). Everything above this layer — hooks, prompt
resolution, the agent provider — only ever calls `handle.exec(...)` and
`handle.copy_file_in/out(...)`; it has no idea the sandbox happens to be a
Docker container.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from sandcastle.types import ExecResult, Mount


@dataclass(frozen=True)
class BindMountCreateOptions:
    worktree_path: str
    host_repo_path: str
    mounts: tuple[Mount, ...] = ()
    env: dict[str, str] = field(default_factory=dict)


class SandboxHandle(Protocol):
    worktree_path: str

    def exec(
        self,
        command: str,
        *,
        cwd: str | None = None,
        sudo: bool = False,
        stdin: str | None = None,
        on_line: Callable[[str], None] | None = None,
        timeout_seconds: float | None = None,
    ) -> ExecResult: ...

    def copy_file_in(self, host_path: str, sandbox_path: str) -> None: ...

    def copy_file_out(self, sandbox_path: str, host_path: str) -> None: ...

    def close(self) -> None: ...


class SandboxProvider(Protocol):
    name: str
    env: dict[str, str]

    def create(self, options: BindMountCreateOptions) -> SandboxHandle: ...
