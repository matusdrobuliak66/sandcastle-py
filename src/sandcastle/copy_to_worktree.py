"""Copy host-relative paths into a git worktree before the sandbox starts.

Necessary because `git worktree add` only brings tracked files — anything
gitignored (dependency caches, local-only config like a `pi` model-provider
file) has to be copied in explicitly.
"""

from __future__ import annotations

import os
import shutil


def copy_paths_into_worktree(host_repo_dir: str, worktree_path: str, relative_paths: list[str]) -> None:
    for rel_path in relative_paths:
        src = os.path.join(host_repo_dir, rel_path)
        dst = os.path.join(worktree_path, rel_path)
        if not os.path.exists(src):
            continue
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
