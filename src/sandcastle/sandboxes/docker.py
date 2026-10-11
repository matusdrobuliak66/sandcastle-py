"""The Docker sandbox provider.

Shells out to the `docker` CLI via `subprocess` only — no docker-py, no
Engine API/socket — mirroring the real JS sandcastle's approach exactly
(confirmed by reading its compiled source). This keeps the dependency
surface at zero and the behavior easy to reason about: every operation is
a `docker` command you could type yourself.
"""

from __future__ import annotations

import atexit
import os
import re
import shlex
import signal
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass

from sandcastle.errors import DockerError
from sandcastle.protocols.sandbox_provider import BindMountCreateOptions
from sandcastle.sandboxes.network_lockdown import NetworkLockdown
from sandcastle.types import ExecResult, Mount

_DEFAULT_IMAGE_PATTERN = "sandcastle-py:{repo_dir_name}"

# Container names registered here get force-removed if the process exits
# without a clean `handle.close()` — the same safety net the JS provider
# has (a sync SIGTERM/exit handler alongside the normal stop+rm path).
_active_containers: set[str] = set()
_active_containers_lock = threading.Lock()
_shutdown_hook_installed = False


def _force_remove_all() -> None:
    with _active_containers_lock:
        names = list(_active_containers)
    for name in names:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            check=False,
        )


def _install_shutdown_hook() -> None:
    global _shutdown_hook_installed
    if _shutdown_hook_installed:
        return
    _shutdown_hook_installed = True
    atexit.register(_force_remove_all)

    def _on_signal(signum: int, frame: object) -> None:
        _force_remove_all()
        os._exit(1)

    try:
        signal.signal(signal.SIGTERM, _on_signal)
    except (ValueError, OSError):
        # Not in the main thread, or platform doesn't support it — the
        # atexit handler still covers the common case.
        pass


def _run(args: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise DockerError(
            f"`{' '.join(args)}` failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    return proc


@dataclass
class DockerSandboxHandle:
    container_name: str
    worktree_path: str
    container_uid: int
    container_gid: int

    def exec(
        self,
        command: str,
        *,
        cwd: str | None = None,
        sudo: bool = False,
        stdin: str | None = None,
        on_line: Callable[[str], None] | None = None,
        timeout_seconds: float | None = None,
    ) -> ExecResult:
        args = ["docker", "exec"]
        if stdin is not None:
            args.append("-i")
        if cwd:
            args += ["-w", cwd]
        user = "0:0" if sudo else f"{self.container_uid}:{self.container_gid}"
        args += ["--user", user, self.container_name, "sh", "-c", command]

        if on_line is None:
            proc = subprocess.run(
                args,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            return ExecResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)

        # Streamed mode: run the subprocess, read stdout line-by-line on a
        # background thread so on_line() is called live, while still
        # collecting the full text for the returned ExecResult.
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        stdout_lines: list[str] = []

        def _pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                stdout_lines.append(line)
                on_line(line.rstrip("\n"))

        pump_thread = threading.Thread(target=_pump, daemon=True)
        pump_thread.start()

        if stdin is not None:
            assert proc.stdin is not None
            proc.stdin.write(stdin)
            proc.stdin.close()

        stderr_text = ""
        try:
            _, stderr_text = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        pump_thread.join(timeout=5)

        return ExecResult(
            stdout="".join(stdout_lines),
            stderr=stderr_text or "",
            exit_code=proc.returncode or 0,
        )

    def copy_file_in(self, host_path: str, sandbox_path: str) -> None:
        _run(["docker", "cp", host_path, f"{self.container_name}:{sandbox_path}"])

    def copy_file_out(self, sandbox_path: str, host_path: str) -> None:
        _run(["docker", "cp", f"{self.container_name}:{sandbox_path}", host_path])

    def close(self) -> None:
        with _active_containers_lock:
            _active_containers.discard(self.container_name)
        subprocess.run(["docker", "stop", self.container_name], capture_output=True, check=False)
        subprocess.run(["docker", "rm", self.container_name], capture_output=True, check=False)


class DockerSandboxProvider:
    name = "docker"

    def __init__(
        self,
        *,
        image_name: str | None = None,
        container_uid: int | None = None,
        container_gid: int | None = None,
        network: str | list[str] | None = None,
        network_lockdown: NetworkLockdown | None = None,
        mounts: list[Mount] | None = None,
        env: dict[str, str] | None = None,
        cpus: float | None = None,
    ) -> None:
        self.image_name = image_name
        self.container_uid = container_uid if container_uid is not None else os.getuid()
        self.container_gid = container_gid if container_gid is not None else os.getgid()
        self.network = network
        self.network_lockdown = network_lockdown
        self.mounts = mounts or []
        self.env = dict(env or {})
        self.cpus = cpus

    def _resolve_image_name(self, host_repo_path: str) -> str:
        if self.image_name:
            return self.image_name
        repo_dir_name = os.path.basename(os.path.abspath(host_repo_path))
        return _DEFAULT_IMAGE_PATTERN.format(repo_dir_name=repo_dir_name)

    def _check_image_uid(self, image: str) -> None:
        proc = _run(["docker", "image", "inspect", image, "--format", "{{.Config.User}}"])
        configured_user = proc.stdout.strip()
        if not configured_user:
            return
        uid_part = configured_user.split(":", 1)[0]
        if uid_part and uid_part != str(self.container_uid):
            raise DockerError(
                f"image '{image}' was built with UID {uid_part}, but this sandbox "
                f"is configured for UID {self.container_uid}. Rebuild the image "
                f"with --build-arg AGENT_UID={self.container_uid}."
            )

    def create(self, options: BindMountCreateOptions) -> DockerSandboxHandle:
        _install_shutdown_hook()
        image = self._resolve_image_name(options.host_repo_path)
        self._check_image_uid(image)

        container_name = f"sandcastle-{re.sub(r'[^a-zA-Z0-9_.-]', '-', os.path.basename(options.worktree_path))}"

        args = ["docker", "run", "-d", "--name", container_name]
        if self.network_lockdown is not None:
            args += ["--cap-add=NET_ADMIN"]
        for key, value in {**self.env, **options.env}.items():
            args += ["-e", f"{key}={value}"]
        workdir = "/home/agent/workspace"
        args += ["-v", f"{options.worktree_path}:{workdir}"]
        for mount in [*self.mounts, *options.mounts]:
            suffix = ":ro" if mount.readonly else ""
            args += ["-v", f"{mount.host_path}:{mount.sandbox_path}{suffix}"]
        args += ["-w", workdir, "--user", f"{self.container_uid}:{self.container_gid}"]
        if self.network:
            networks = [self.network] if isinstance(self.network, str) else self.network
            for net in networks:
                args += ["--network", net]
        if self.cpus:
            args += ["--cpus", str(self.cpus)]
        args.append(image)

        _run(args)
        with _active_containers_lock:
            _active_containers.add(container_name)

        handle = DockerSandboxHandle(
            container_name=container_name,
            worktree_path=workdir,
            container_uid=self.container_uid,
            container_gid=self.container_gid,
        )

        if self.network_lockdown is not None:
            lockdown_result = handle.exec(self.network_lockdown.build_script(), sudo=True)
            if lockdown_result.exit_code != 0:
                handle.close()
                raise DockerError(
                    f"failed to apply network lockdown: {lockdown_result.stderr.strip()}"
                )

        for mount in [*self.mounts, *options.mounts]:
            prep = handle.exec(
                f"mkdir -p {shlex.quote(mount.sandbox_path)} && "
                f"chown {self.container_uid}:{self.container_gid} {shlex.quote(mount.sandbox_path)}",
                sudo=True,
            )
            if prep.exit_code != 0:
                handle.close()
                raise DockerError(f"failed to prepare mount {mount.sandbox_path}: {prep.stderr.strip()}")

        return handle
