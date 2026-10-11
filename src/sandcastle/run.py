"""Public entry points: `create_sandbox()` / `Sandbox` and the `run()`
convenience function that creates, runs once, and closes."""

from __future__ import annotations

import os
from typing import Self

from sandcastle import orchestrate
from sandcastle.branch_strategies.local_branch import LocalBranchStrategy
from sandcastle.copy_to_worktree import copy_paths_into_worktree
from sandcastle.errors import PromptError
from sandcastle.hooks import run_host_hooks, run_sandbox_hooks
from sandcastle.log import RunLogger
from sandcastle.prompt import substitute_prompt_args
from sandcastle.protocols.agent_provider import AgentProvider
from sandcastle.protocols.branch_strategy import (
    BranchStrategy,
    WorktreeContext,
    WorktreeInfo,
)
from sandcastle.protocols.sandbox_provider import (
    BindMountCreateOptions,
    SandboxHandle,
    SandboxProvider,
)
from sandcastle.types import RunResult, SandboxHooks
from sandcastle.worktree import current_branch

DEFAULT_COMPLETION_SIGNAL = "<promise>COMPLETE</promise>"


class Sandbox:
    def __init__(
        self,
        *,
        sandbox_provider: SandboxProvider,
        branch_strategy: BranchStrategy,
        host_repo_dir: str,
        handle: SandboxHandle,
        worktree_info: WorktreeInfo,
    ) -> None:
        self._sandbox_provider = sandbox_provider
        self._branch_strategy = branch_strategy
        self._host_repo_dir = host_repo_dir
        self._handle = handle
        self._worktree_info = worktree_info

    @property
    def branch(self) -> str:
        return self._worktree_info.branch

    @property
    def worktree_path(self) -> str:
        return self._worktree_info.path

    def run(
        self,
        *,
        name: str,
        agent: AgentProvider,
        prompt: str | None = None,
        prompt_file: str | None = None,
        prompt_args: dict[str, str] | None = None,
        max_iterations: int = 1,
        completion_signal: str | tuple[str, ...] = DEFAULT_COMPLETION_SIGNAL,
        shell_expansion_timeout_seconds: float = 30.0,
        log_path: str | None = None,
    ) -> RunResult:
        if (prompt is None) == (prompt_file is None):
            raise PromptError("exactly one of prompt or prompt_file must be provided")
        if prompt is not None and prompt_args:
            raise PromptError("prompt_args is only valid with prompt_file (inline prompt is literal)")

        signals = (completion_signal,) if isinstance(completion_signal, str) else tuple(completion_signal)

        logger = RunLogger(path=log_path)

        if prompt_file is not None:
            resolved_path = prompt_file if os.path.isabs(prompt_file) else os.path.join(os.getcwd(), prompt_file)
            with open(resolved_path, encoding="utf-8") as f:
                template = f.read()
            substituted = substitute_prompt_args(
                template,
                prompt_args or {},
                source_branch=self.branch,
                target_branch=current_branch(self._host_repo_dir),
            )
        else:
            assert prompt is not None
            substituted = prompt

        iterations, matched_signal = orchestrate.run_iterations(
            sandbox=self._handle,
            agent=agent,
            substituted_template=substituted,
            sandbox_cwd=self._handle.worktree_path,
            max_iterations=max_iterations,
            completion_signals=signals,
            shell_expansion_timeout_seconds=shell_expansion_timeout_seconds,
            logger=logger,
            name=name,
        )

        finalize_result = self._branch_strategy.finalize(self._worktree_info, self._host_repo_dir)

        return RunResult(
            name=name,
            branch=finalize_result.branch,
            commits=finalize_result.commits,
            iterations=tuple(iterations),
            completion_signal=matched_signal,
        )

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def create_sandbox(
    *,
    branch: str,
    sandbox: SandboxProvider,
    hooks: SandboxHooks | None = None,
    copy_to_worktree: list[str] | None = None,
    host_repo_dir: str | None = None,
    branch_strategy: BranchStrategy | None = None,
) -> Sandbox:
    host_repo_dir = host_repo_dir or os.getcwd()
    hooks = hooks or SandboxHooks()
    strategy = branch_strategy or LocalBranchStrategy(branch)

    worktree_info = strategy.create_worktree(WorktreeContext(host_repo_dir=host_repo_dir))

    if copy_to_worktree:
        copy_paths_into_worktree(host_repo_dir, worktree_info.path, copy_to_worktree)

    run_host_hooks(hooks.host_on_worktree_ready, cwd=worktree_info.path)

    handle = sandbox.create(
        BindMountCreateOptions(worktree_path=worktree_info.path, host_repo_path=host_repo_dir)
    )

    run_sandbox_hooks(hooks.sandbox_on_sandbox_ready, handle)
    run_host_hooks(hooks.host_on_sandbox_ready, cwd=worktree_info.path)

    return Sandbox(
        sandbox_provider=sandbox,
        branch_strategy=strategy,
        host_repo_dir=host_repo_dir,
        handle=handle,
        worktree_info=worktree_info,
    )


def run(
    *,
    branch: str,
    sandbox: SandboxProvider,
    agent: AgentProvider,
    name: str = "run",
    hooks: SandboxHooks | None = None,
    copy_to_worktree: list[str] | None = None,
    host_repo_dir: str | None = None,
    branch_strategy: BranchStrategy | None = None,
    **run_kwargs: object,
) -> RunResult:
    """Convenience wrapper: create_sandbox() + run() + close() in one call."""
    with create_sandbox(
        branch=branch,
        sandbox=sandbox,
        hooks=hooks,
        copy_to_worktree=copy_to_worktree,
        host_repo_dir=host_repo_dir,
        branch_strategy=branch_strategy,
    ) as sb:
        return sb.run(name=name, agent=agent, **run_kwargs)  # type: ignore[arg-type]
