"""Unit tests for git worktree creation and commit collection. No Docker
required — operates against a scratch git repo created in a temp dir."""

from __future__ import annotations

import subprocess

import pytest

from sandcastle.errors import WorktreeError
from sandcastle.worktree import (
    branch_exists,
    collect_commits,
    create_worktree_for_branch,
    current_branch,
    is_branch_checked_out_elsewhere,
    rev_parse_head,
)


def _git(repo_dir: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo_dir, *args], check=True, capture_output=True)


@pytest.fixture
def scratch_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo_dir_str = str(repo_dir)
    _git(repo_dir_str, "init", "-b", "main")
    _git(repo_dir_str, "config", "user.email", "test@example.com")
    _git(repo_dir_str, "config", "user.name", "Test")
    (repo_dir / "README.md").write_text("hello\n")
    _git(repo_dir_str, "add", "README.md")
    _git(repo_dir_str, "commit", "-m", "initial")
    return repo_dir_str


def test_rev_parse_head_returns_sha(scratch_repo):
    sha = rev_parse_head(scratch_repo)
    assert len(sha) == 40


def test_current_branch(scratch_repo):
    assert current_branch(scratch_repo) == "main"


def test_branch_exists_false_for_unknown(scratch_repo):
    assert branch_exists(scratch_repo, "does-not-exist") is False


def test_create_worktree_new_branch(scratch_repo, tmp_path):
    worktree_path = str(tmp_path / "wt")
    create_worktree_for_branch(scratch_repo, "feature/x", worktree_path)
    assert branch_exists(scratch_repo, "feature/x")
    import os

    assert os.path.isdir(worktree_path)


def test_create_worktree_rejects_double_checkout(scratch_repo, tmp_path):
    create_worktree_for_branch(scratch_repo, "feature/y", str(tmp_path / "wt1"))
    with pytest.raises(WorktreeError):
        create_worktree_for_branch(scratch_repo, "feature/y", str(tmp_path / "wt2"))


def test_is_branch_checked_out_elsewhere(scratch_repo, tmp_path):
    assert is_branch_checked_out_elsewhere(scratch_repo, "feature/z") is False
    create_worktree_for_branch(scratch_repo, "feature/z", str(tmp_path / "wt"))
    assert is_branch_checked_out_elsewhere(scratch_repo, "feature/z") is True


def test_collect_commits_matches_new_commits_in_order(scratch_repo, tmp_path):
    base_head = rev_parse_head(scratch_repo)
    worktree_path = str(tmp_path / "wt")
    create_worktree_for_branch(scratch_repo, "feature/w", worktree_path)

    (tmp_path / "wt" / "a.txt").write_text("a\n")
    _git(worktree_path, "add", "a.txt")
    _git(worktree_path, "commit", "-m", "add a")
    first_sha = rev_parse_head(worktree_path)

    (tmp_path / "wt" / "b.txt").write_text("b\n")
    _git(worktree_path, "add", "b.txt")
    _git(worktree_path, "commit", "-m", "add b")
    second_sha = rev_parse_head(worktree_path)

    commits = collect_commits(scratch_repo, base_head, "feature/w")
    assert [c.sha for c in commits] == [first_sha, second_sha]


def test_collect_commits_empty_when_no_new_commits(scratch_repo, tmp_path):
    base_head = rev_parse_head(scratch_repo)
    create_worktree_for_branch(scratch_repo, "feature/v", str(tmp_path / "wt"))
    commits = collect_commits(scratch_repo, base_head, "feature/v")
    assert commits == ()
