"""Stub for the `merge-to-head` strategy (temp branch in a worktree, merged
back to HEAD when done, temp branch deleted after). Not implemented in v1
— preserved so the BranchStrategy dispatch shape already accounts for it.
"""

from __future__ import annotations

from sandcastle.protocols.branch_strategy import (
    BranchStrategy,
    FinalizeResult,
    WorktreeContext,
    WorktreeInfo,
)

_NOT_IMPLEMENTED = (
    "MergeToHeadBranchStrategy is not implemented in sandcastle-py v1 — "
    "only LocalBranchStrategy (type='branch') ships. 'merge-to-head' means "
    "a temp branch that gets merged back to HEAD and deleted when the run "
    "finishes; add it if/when you want automation that commits straight "
    "to your working branch."
)


class MergeToHeadBranchStrategy(BranchStrategy):
    type = "merge-to-head"

    def create_worktree(self, ctx: WorktreeContext) -> WorktreeInfo:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def finalize(self, worktree_info: WorktreeInfo, host_repo_dir: str) -> FinalizeResult:
        raise NotImplementedError(_NOT_IMPLEMENTED)
