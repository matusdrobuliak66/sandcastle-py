"""Integration tests for DockerSandboxProvider. Requires a local Docker
daemon and the `sandcastle-py:test` image (see docker/Dockerfile)."""

from __future__ import annotations

import pytest

from sandcastle.protocols.sandbox_provider import BindMountCreateOptions
from sandcastle.sandboxes.docker import DockerSandboxProvider

pytestmark = pytest.mark.docker

IMAGE = "sandcastle-py:test"


@pytest.fixture
def worktree(tmp_path):
    d = tmp_path / "worktree"
    d.mkdir()
    return str(d)


def test_create_exec_close(worktree):
    provider = DockerSandboxProvider(image_name=IMAGE)
    handle = provider.create(
        BindMountCreateOptions(worktree_path=worktree, host_repo_path=worktree)
    )
    try:
        result = handle.exec("echo hello")
        assert result.exit_code == 0
        assert result.stdout.strip() == "hello"
    finally:
        handle.close()


def test_exec_nonzero_exit_reported(worktree):
    provider = DockerSandboxProvider(image_name=IMAGE)
    handle = provider.create(
        BindMountCreateOptions(worktree_path=worktree, host_repo_path=worktree)
    )
    try:
        result = handle.exec("exit 3")
        assert result.exit_code == 3
    finally:
        handle.close()


def test_exec_streams_lines_via_on_line(worktree):
    provider = DockerSandboxProvider(image_name=IMAGE)
    handle = provider.create(
        BindMountCreateOptions(worktree_path=worktree, host_repo_path=worktree)
    )
    lines: list[str] = []
    try:
        handle.exec("printf 'a\\nb\\nc\\n'", on_line=lines.append)
    finally:
        handle.close()
    assert lines == ["a", "b", "c"]


def test_worktree_bind_mount_visible_in_container(worktree):
    with open(f"{worktree}/marker.txt", "w") as f:
        f.write("present")
    provider = DockerSandboxProvider(image_name=IMAGE)
    handle = provider.create(
        BindMountCreateOptions(worktree_path=worktree, host_repo_path=worktree)
    )
    try:
        result = handle.exec("cat marker.txt")
        assert result.stdout.strip() == "present"
    finally:
        handle.close()
