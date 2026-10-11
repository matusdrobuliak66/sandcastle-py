# sandcastle-py

A minimal Python reimplementation of a narrow slice of `@ai-hero/sandcastle`:
run the `pi` coding-agent CLI inside a locked-down Docker sandbox, driven by
a self-hosted model, with a local file-based issue tracker instead of
GitHub. See `PLAN.md` for the full design and build status.

## Quick start

```bash
uv sync
docker build -t sandcastle-py:test -f docker/Dockerfile \
  --build-arg AGENT_UID=$(id -u) --build-arg AGENT_GID=$(id -g) docker/

cd examples/sequential_reviewer
cp pi-models.json.example pi-models.json   # fill in your model host IP
uv run --project .. python main.py
```

## Layout

- `src/sandcastle/` — the library: `AgentProvider`/`SandboxProvider`/
  `BranchStrategy` protocols, with `PiAgentProvider`, `DockerSandboxProvider`,
  and `LocalBranchStrategy` as v1's only concrete implementations.
- `docker/Dockerfile` — the sandbox image (`pi` + `iptables` + an unprivileged
  `agent` user).
- `examples/sequential_reviewer/` — a runnable implement→review loop against
  local `issues/open/*.md` files.
- `tests/` — unit tests (no Docker) and integration tests (`-m docker`,
  requires a local Docker daemon and the built image).

## Testing

```bash
uv run pytest -q                # everything, including docker-marked tests
uv run pytest -q -m "not docker"  # unit tests only, no Docker required
```
