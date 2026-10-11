"""Exceptions raised by sandcastle."""


class SandcastleError(Exception):
    """Base class for all sandcastle errors."""


class DockerError(SandcastleError):
    """A `docker` CLI invocation failed."""


class WorktreeError(SandcastleError):
    """Git worktree creation or commit collection failed."""


class PromptError(SandcastleError):
    """Prompt resolution (substitution or shell-expansion) failed."""


class HookError(SandcastleError):
    """A lifecycle hook failed (non-zero exit)."""


class HookTimeoutError(HookError):
    """A lifecycle hook exceeded its timeout."""


class ShellExpansionError(SandcastleError):
    """A `` !`command` `` expansion exited non-zero or timed out."""
