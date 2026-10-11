"""The `branch` strategy: fully local, no auto-merge, no push.

This is v1's only real BranchStrategy implementation — the lowest-blast-
radius option. The agent's commits land on a named branch in a disposable
git worktree; nothing is merged back to HEAD and nothing is pushed unless
the caller does that explicitly afterward.
"""

from __future__ import annotations

import os

from sandcastle.protocols.branch_strategy import (
    BranchStrategy,
    FinalizeResult,
    WorktreeContext,
    WorktreeInfo,
)
from sandcastle.worktree import (
    collect_commits,
    create_worktree_for_branch,
    rev_parse_head,
)


class LocalBranchStrategy(BranchStrategy):
    type = "branch"

    def __init__(self, branch: str, base_branch: str | None = None) -> None:
        self.branch = branch
        self.base_branch = base_branch

    def create_worktree(self, ctx: WorktreeContext) -> WorktreeInfo:
        base_head = rev_parse_head(ctx.host_repo_dir)
        safe_name = self.branch.replace("/", "-")
        worktree_path = os.path.join(ctx.host_repo_dir, ".sandcastle", "worktrees", safe_name)
        os.makedirs(os.path.dirname(worktree_path), exist_ok=True)
        create_worktree_for_branch(
            ctx.host_repo_dir, self.branch, worktree_path, self.base_branch
        )
        return WorktreeInfo(path=worktree_path, branch=self.branch, base_head=base_head)

    def finalize(self, worktree_info: WorktreeInfo, host_repo_dir: str) -> FinalizeResult:
        commits = collect_commits(host_repo_dir, worktree_info.base_head, worktree_info.branch)
        return FinalizeResult(branch=worktree_info.branch, commits=commits)
