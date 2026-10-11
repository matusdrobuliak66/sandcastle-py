"""Integration test for the network lockdown, driven through
DockerSandboxProvider (not raw `docker` commands) to confirm the mechanism
is wired into the real lifecycle at the right point.

Deliberately does not depend on the live, external vLLM endpoint — an
"allowed" target is a second local container on the same bridge network,
so the test is self-contained and deterministic. The "blocked" target is
a well-known public IP (1.1.1.1) that must NOT be reachable."""

from __future__ import annotations

import subprocess

import pytest

from sandcastle.protocols.sandbox_provider import BindMountCreateOptions
from sandcastle.sandboxes.docker import DockerSandboxProvider
from sandcastle.sandboxes.network_lockdown import NetworkLockdown

pytestmark = pytest.mark.docker

IMAGE = "sandcastle-py:test"
TARGET_CONTAINER = "sandcastle-py-lockdown-target"
TARGET_PORT = 8000


@pytest.fixture
def allowed_target():
    subprocess.run(["docker", "rm", "-f", TARGET_CONTAINER], capture_output=True, check=False)
    subprocess.run(
        [
            "docker", "run", "-d", "--name", TARGET_CONTAINER,
            "--entrypoint", "python3", IMAGE, "-m", "http.server", str(TARGET_PORT),
        ],
        check=True, capture_output=True,
    )
    ip_proc = subprocess.run(
        [
            "docker", "inspect", "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", TARGET_CONTAINER,
        ],
        check=True, capture_output=True, text=True,
    )
    ip = ip_proc.stdout.strip()
    assert ip, "target container has no IP yet"
    yield ip
    subprocess.run(["docker", "rm", "-f", TARGET_CONTAINER], capture_output=True, check=False)


@pytest.fixture
def worktree(tmp_path):
    d = tmp_path / "worktree"
    d.mkdir()
    return str(d)


def test_lockdown_allows_allowlisted_target_blocks_everything_else(worktree, allowed_target):
    provider = DockerSandboxProvider(
        image_name=IMAGE,
        network_lockdown=NetworkLockdown(allow_host=allowed_target, allow_port=TARGET_PORT),
    )
    handle = provider.create(
        BindMountCreateOptions(worktree_path=worktree, host_repo_path=worktree)
    )
    try:
        allowed = handle.exec(
            f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' http://{allowed_target}:{TARGET_PORT}/"
        )
        assert allowed.stdout.strip() == "200"

        blocked = handle.exec("curl -s -m 5 -o /dev/null -w '%{http_code}' https://1.1.1.1")
        assert blocked.stdout.strip() != "200"
    finally:
        handle.close()


def test_no_lockdown_means_unrestricted_egress(worktree, allowed_target):
    # Sanity check for the test setup itself: without a lockdown, the
    # allowed target must still be reachable, same as with one.
    provider = DockerSandboxProvider(image_name=IMAGE)
    handle = provider.create(
        BindMountCreateOptions(worktree_path=worktree, host_repo_path=worktree)
    )
    try:
        result = handle.exec(
            f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' http://{allowed_target}:{TARGET_PORT}/"
        )
        assert result.stdout.strip() == "200"
    finally:
        handle.close()
