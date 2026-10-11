"""The BranchStrategy abstraction.

Controls how an agent's git work relates to the host repo's real branches.
v1 ships only `LocalBranchStrategy` (fully local, no auto-merge, no push —
the lowest-blast-radius option). `HeadBranchStrategy` and
`MergeToHeadBranchStrategy` are typed stubs preserving the dispatch shape
for later, without the complexity of building them before they're needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sandcastle.types import Commit


@dataclass(frozen=True)
class WorktreeContext:
    host_repo_dir: str
    name: str | None = None


@dataclass(frozen=True)
class WorktreeInfo:
    path: str
    branch: str
    base_head: str


@dataclass(frozen=True)
class FinalizeResult:
    branch: str
    commits: tuple[Commit, ...]


class BranchStrategy(ABC):
    type: str

    @abstractmethod
    def create_worktree(self, ctx: WorktreeContext) -> WorktreeInfo: ...

    @abstractmethod
    def finalize(self, worktree_info: WorktreeInfo, host_repo_dir: str) -> FinalizeResult: ...
