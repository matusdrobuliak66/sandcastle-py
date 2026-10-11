"""Git worktree creation and commit collection.

Worktrees share the same object database and refs as the main repo, so
commit collection always runs against `host_repo_dir` (not the worktree
path) — `git rev-list <base>..refs/heads/<branch>` sees the branch's new
commits regardless of which worktree (if any) currently has it checked out.
"""

from __future__ import annotations

import subprocess

from sandcastle.errors import WorktreeError
from sandcastle.types import Commit


def _git(repo_dir: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", repo_dir, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise WorktreeError(f"`git {' '.join(args)}` failed: {proc.stderr.strip()}")
    return proc


def rev_parse_head(repo_dir: str) -> str:
    return _git(repo_dir, "rev-parse", "HEAD").stdout.strip()


def branch_exists(repo_dir: str, branch: str) -> bool:
    proc = _git(repo_dir, "rev-parse", "--verify", f"refs/heads/{branch}", check=False)
    return proc.returncode == 0


def is_branch_checked_out_elsewhere(repo_dir: str, branch: str) -> bool:
    proc = _git(repo_dir, "worktree", "list", "--porcelain")
    target = f"refs/heads/{branch}"
    for block in proc.stdout.split("\n\n"):
        if any(line.strip() == f"branch {target}" for line in block.splitlines()):
            return True
    return False


def create_worktree_for_branch(
    repo_dir: str,
    branch: str,
    worktree_path: str,
    base_branch: str | None = None,
) -> None:
    if is_branch_checked_out_elsewhere(repo_dir, branch):
        raise WorktreeError(
            f"branch '{branch}' is already checked out in another worktree; "
            "git refuses to check out the same branch twice."
        )
    if branch_exists(repo_dir, branch):
        _git(repo_dir, "worktree", "add", worktree_path, branch)
    else:
        _git(repo_dir, "worktree", "add", "-b", branch, worktree_path, base_branch or "HEAD")


def collect_commits(repo_dir: str, base_head: str, branch: str) -> tuple[Commit, ...]:
    proc = _git(repo_dir, "rev-list", f"{base_head}..refs/heads/{branch}", "--reverse")
    shas = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return tuple(Commit(sha=sha) for sha in shas)


def current_branch(repo_dir: str) -> str:
    return _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
