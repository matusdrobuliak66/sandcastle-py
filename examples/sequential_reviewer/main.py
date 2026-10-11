"""Sequential implement -> review loop, driven by local issue files instead
of GitHub issues. Direct port of the original JS main.mts.

Usage:
    cp pi-models.json.example pi-models.json   # fill in your model host IP
    uv run python main.py
(run from this directory — `issues/`, prompts, and `pi-models.json` are all
resolved relative to the current working directory)
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlparse

import sandcastle

MAX_ITERATIONS = 10
MODEL = "aws-vllm/qwen3.8-flash-next"
PI_MODELS_CONFIG_PATH = "pi-models.json"


def _network_lockdown_from_pi_models_json(path: str) -> sandcastle.NetworkLockdown:
    """Derive the egress allowlist from pi-models.json itself, rather than
    hardcoding the model host/port a second time — they'd otherwise drift
    out of sync whenever the model endpoint moves (as happened once during
    development of this example)."""
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    base_url = config["providers"]["aws-vllm"]["baseUrl"]
    parsed = urlparse(base_url)
    return sandcastle.NetworkLockdown(allow_host=parsed.hostname, allow_port=parsed.port)


def main() -> None:
    network_lockdown = _network_lockdown_from_pi_models_json(PI_MODELS_CONFIG_PATH)

    hooks = sandcastle.SandboxHooks(
        sandbox_on_sandbox_ready=(
            sandcastle.HookSpec(command="mkdir -p ~/.pi/agent"),
            sandcastle.HookSpec(command="cp pi-models.json ~/.pi/agent/models.json"),
        )
    )
    copy_to_worktree = [PI_MODELS_CONFIG_PATH]

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n=== Iteration {iteration}/{MAX_ITERATIONS} ===\n")
        branch = f"sandcastle/sequential-reviewer/{int(time.time() * 1000)}"

        sandbox = sandcastle.create_sandbox(
            branch=branch,
            sandbox=sandcastle.DockerSandboxProvider(
                image_name="sandcastle-py:test",
                network_lockdown=network_lockdown,
            ),
            hooks=hooks,
            copy_to_worktree=copy_to_worktree,
        )
        try:
            implement = sandbox.run(
                name="implementer",
                max_iterations=1,
                agent=sandcastle.PiAgentProvider(MODEL, thinking="low"),
                prompt_file="implement-prompt.md",
                log_path=f".sandcastle/logs/{branch.replace('/', '-')}-implementer.log",
            )
            if not implement.commits:
                print("Implementation agent made no commits. Stopping.")
                break

            print(f"\nImplementation complete on branch: {branch}")
            print(f"Commits: {len(implement.commits)}")

            sandbox.run(
                name="reviewer",
                max_iterations=1,
                agent=sandcastle.PiAgentProvider(MODEL, thinking="low"),
                prompt_file="review-prompt.md",
                prompt_args={"BRANCH": branch},
                log_path=f".sandcastle/logs/{branch.replace('/', '-')}-reviewer.log",
            )
            print("\nReview complete.")
        finally:
            sandbox.close()

    print("\nAll done.")


if __name__ == "__main__":
    main()
