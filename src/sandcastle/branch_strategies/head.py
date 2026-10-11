"""Stub for the `head` strategy (no worktree, operates on the current
checkout directly, bind-mount only). Not implemented in v1 — preserved so
the BranchStrategy dispatch shape already accounts for it.
"""

from __future__ import annotations

from sandcastle.protocols.branch_strategy import (
    BranchStrategy,
    FinalizeResult,
    WorktreeContext,
    WorktreeInfo,
)

_NOT_IMPLEMENTED = (
    "HeadBranchStrategy is not implemented in sandcastle-py v1 — only "
    "LocalBranchStrategy (type='branch') ships. 'head' means operating "
    "directly on the host's current checkout with no worktree indirection; "
    "add it if/when you need fast local iteration without branch isolation."
)


class HeadBranchStrategy(BranchStrategy):
    type = "head"

    def create_worktree(self, ctx: WorktreeContext) -> WorktreeInfo:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def finalize(self, worktree_info: WorktreeInfo, host_repo_dir: str) -> FinalizeResult:
        raise NotImplementedError(_NOT_IMPLEMENTED)
