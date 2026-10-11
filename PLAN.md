# sandcastle-py — implementation plan & status

A from-scratch Python reimplementation of a narrow slice of `@ai-hero/sandcastle`:
orchestrate the `pi` coding-agent CLI inside a Docker sandbox, with a self-hosted
vLLM model, a local file-based issue tracker (no GitHub), and network egress
locked down to just the model endpoint (no general internet access from the
container in v1).

Three abstractions are kept as real Protocols/ABCs (for future extension)
even though v1 ships exactly one concrete implementation of each:
`AgentProvider` (→ `pi`), `SandboxProvider` (→ Docker), `BranchStrategy`
(→ local named branch, no auto-merge/push).

This file is the live status tracker for the build — updated as work lands,
not just a one-time design doc. Status legend: `[ ]` not started, `[~]` in
progress, `[x]` done.

## Current status (at a glance)

Library is fully implemented and self-tested: 20 unit tests + 6 Docker
integration tests pass, `ruff check .` is clean. The `examples/sequential_reviewer/`
implement→review loop is fully built (prompts, toy project, seeded issue)
but **not yet run end-to-end**, because the external vLLM endpoint
(`<vllm-host>:8000`) is currently unreachable from this machine — this
was true even via a direct `curl` from the host, confirmed not a bug in
the lockdown mechanism (see §3). Everything else is ready to go the moment
that endpoint is back up: `uv run python examples/sequential_reviewer/main.py`.

Remaining before calling v1 "done": run the live e2e cycle once the model
endpoint is reachable again, and decide whether `env_file.py` needs wiring
up anywhere (currently unused — no `.env`-consuming code path exists yet).

## Decisions locked in

- Network: block everything except the model endpoint (raw IP:port, no DNS
  needed) via `--cap-add=NET_ADMIN` + in-container `iptables`, applied by a
  root `docker exec` immediately after container start, before any hook or
  agent work. Rejected: proxy sidecar (same mechanism + more moving parts),
  host-level macOS firewall (not container-specific), `pi --offline` (only
  suppresses pi's own update check, not a sandboxing control).
- Issue tracker: plain files, `issues/open/*.md` / `issues/closed/*.md`,
  YAML frontmatter, manipulated entirely by the agent's own tools — no
  tracker code in the library.
- Docker driven via `subprocess` calls to the `docker` CLI only — no
  docker-py, no socket API — mirroring the real JS implementation.
- Packaging: `uv` + `pyproject.toml`, Python 3.13, zero runtime dependencies
  (stdlib only).
- v1 scope includes the full implement→review loop, not just the bare
  single-run primitive.

## Empirical findings (Phase 0 — done)

- **`@file` prompt delivery hangs** under `-p` with no positional message —
  presumably waiting for an explicit message string in addition to the
  attachment. **Use stdin instead**: `echo "<prompt>" | pi -p --mode json
  --model <model> --thinking <level>` — confirmed working against the live
  vLLM endpoint, matches the JS provider's actual design (`stdin: prompt`).
- Real `--mode json` event schema (top-level `type` values seen): `session`
  (`{id, version, timestamp, cwd}`), `agent_start`, `turn_start`,
  `message_start`/`message_end` (`{message: {role, content, ...}}`),
  `message_update` (`{assistantMessageEvent: {type, contentIndex, delta?,
  content?, partial}, message}` — nested type is `thinking_start/delta/end`,
  `text_start/delta/end`, or `toolcall_start/delta/end`),
  `tool_execution_start` (`{toolCallId, toolName, args}`),
  `tool_execution_update`, `tool_execution_end` (`{toolCallId, toolName,
  result: {content: [{type:"text", text}]}, isError}`), `turn_end`
  (`{message, toolResults}`), `agent_end` (`{messages}`). Parser built
  against this: normalize `tool_execution_start`/`_end` → `ToolCallEvent`/
  `ResultEvent`, `text_delta` → `TextEvent`, `session` → `SessionIdEvent`,
  everything else ignored (not fatal) per the "unknown types are tolerated"
  design rule.

## Build checklist

### 0. Empirical check
- [x] Run `pi ... --mode json` against the live vLLM endpoint, capture raw
      JSON lines (see "Empirical findings" above). `@file` delivery hangs;
      stdin works and is what the library uses.

### 1. Project scaffold
- [x] `pyproject.toml`, `.python-version`, `.gitignore`
- [x] `src/sandcastle/` package skeleton, `uv sync` succeeds, `ruff check` clean
- [ ] `README.md` (not written yet — low priority until the example runs end to end)

### 2. Core types & protocols
- [x] `types.py` (ExecResult, Mount, Commit, IterationResult, RunResult, Timeouts, SandboxHooks, HookSpec)
- [x] `errors.py`
- [x] `protocols/agent_provider.py`
- [x] `protocols/sandbox_provider.py`
- [x] `protocols/branch_strategy.py`

### 3. Docker sandbox provider
- [x] `sandboxes/docker.py` — image UID preflight, `run`, `exec` (streamed via
      a background thread + `on_line` callback), `copy_file_in/out`, `stop`/`rm`,
      atexit/SIGTERM safety net (force-removes any container left registered)
- [x] `sandboxes/network_lockdown.py` — `NetworkLockdown` dataclass validates
      the allowed host is a raw IP (fails fast — DNS is blocked so a hostname
      would silently never resolve), builds the iptables script
- [x] `docker/Dockerfile` — pi + iptables + agent user, NET_ADMIN-ready;
      built as `sandcastle-py:test`, no `iptables-nft` issues on this host
- [~] Raw-docker verification: **blocked-host half confirmed** — under the
      lockdown, `curl https://1.1.1.1` and `curl https://example.com` both
      fail (connection timeout), vs. a container with no lockdown at all
      also timing out to the *allowed* endpoint right now. **Allowed-host
      half blocked**: the vLLM server at `<vllm-host>:8000` is currently
      unreachable from the host itself too (`curl` from the Mac directly
      times out, same as from inside any container, locked-down or not) —
      this is an infra/instance issue, not a lockdown bug. `iptables -L
      OUTPUT -n -v` showed 5 packets/300 bytes correctly matching the
      ACCEPT rule for that IP:port before timing out, i.e. the rule let
      the SYN packets out; they just never got a response. **Needs the
      user to confirm the vLLM instance is up / give a current IP before
      this check can be completed.**
- Known simplification vs. the JS original: mount-dir prep does
  `chown <sandbox_path>` (top-level only, not recursive) rather than the
  JS version's "pre-create parent dirs" distinction — fine for v1's one
  use case (copying `pi-models.json` in via `copy_to_worktree`, no extra
  `mounts` configured in the example), revisit if `mounts` gets real use.

### 4. Pi agent provider
- [x] `agents/pi.py` — `build_print_command` (stdin-based, confirmed working),
      `parse_stream_line` (from §0's real schema: `tool_execution_start/end`,
      `message_update.assistantMessageEvent.text_delta`, `session`)

### 5. Branch strategy
- [x] `branch_strategies/local_branch.py` — worktree create + finalize
      (commit collection via `git rev-list base..refs/heads/branch --reverse`,
      run against `host_repo_dir` since worktrees share the object db)
- [x] `branch_strategies/head.py`, `merge_to_head.py` — typed
      `NotImplementedError` stubs

### 6. Prompt pipeline
- [x] `prompt.py` — `{{KEY}}` substitution (host-side, built-ins
      SOURCE_BRANCH/TARGET_BRANCH, no override, single pass so no double-
      substitution risk), `` !`cmd` `` expansion (sandbox-side, concurrent via
      ThreadPoolExecutor, 30s default timeout, right-to-left replacement),
      completion-signal detection (plain substring match)

### 7. Orchestration glue
- [x] `hooks.py` (sequential, not concurrent — simplification, noted in
      code), `copy_to_worktree.py`, `worktree.py`, `orchestrate.py`
      (per-iteration loop: fresh shell-expansion each iteration, matching
      the "stateless iterations" design), `run.py` (public
      `run()`/`create_sandbox()`/`Sandbox`, context-manager support)
- [ ] `env_file.py` — written but not yet wired into anything (no `.env`
      consumer exists until the example script needs one)
- [x] `log.py`

### 8. Example: sequential reviewer
- [x] `examples/sequential_reviewer/main.py` (ported `main.mts`; derives the
      `NetworkLockdown` host/port straight from `pi-models.json`'s
      `baseUrl` instead of hardcoding it a second time — avoids the exact
      config-drift problem we hit once already this session when the vLLM
      IP changed)
- [x] `implement-prompt.md` (local `issues/open/*.md` listing replaces
      `gh issue list`; close step is `git mv` to `issues/closed/` + a
      `## Resolution` note instead of `gh issue close`), `review-prompt.md`
      (ported unchanged in structure — it was never GitHub-specific),
      `CODING_STANDARDS.md`
- [x] `pi-models.json.example`, seeded `issues/open/0001-add-subtract-function.md`,
      toy `src/calc.py` + `tests/test_calc.py` (so the e2e test in §9 has a
      real, minimal verify step: `python3 -m unittest discover -s tests`)

### 9. Tests
- [x] `test_prompt.py` (unit, no docker) — 11 tests, all passing
- [x] `test_worktree.py` (unit, no docker) — 9 tests, all passing
- [x] `test_docker_provider.py` (integration, docker required) — 4 tests,
      all passing: create/exec/close, nonzero exit code reporting, streamed
      `on_line` callback, worktree bind-mount visibility
- [x] `test_network_lockdown.py` (integration, docker required) — redesigned
      from the original plan to be self-contained: instead of depending on
      the live external vLLM endpoint, the "allowed" target is a second
      local container (`python3 -m http.server`) on the same bridge
      network, IP discovered via `docker inspect`. 2 tests passing: lockdown
      allows the allowlisted target and blocks `1.1.1.1`; a sanity check
      confirms the target is reachable with no lockdown too (so a failure
      can't be mistaken for a broken test fixture). This is a *better* test
      than the originally-planned one — deterministic, doesn't depend on
      infra outside this machine. All 6 docker-marked tests pass in ~70s.
- [ ] `test_e2e_sequential_reviewer.py` (full cycle, docker + pi + vLLM
      required) — **blocked on the vLLM endpoint being reachable**, see §3.
      Everything it needs is otherwise ready: `examples/sequential_reviewer/`
      is fully built (main.py, prompts, CODING_STANDARDS.md, seeded issue
      0001, toy src/calc.py + tests/test_calc.py, pi-models.json.example).

## Reference material (read during design, source of truth for porting)

- `~/Projects/sandcastle/node_modules/@ai-hero/sandcastle/dist/chunk-CP3TYXZA.js` — exact `docker` CLI invocations
- `~/Projects/sandcastle/node_modules/@ai-hero/sandcastle/dist/chunk-VOG34SRF.js` — worktree/hook/commit-collection logic
- `~/Projects/sandcastle/.sandcastle/main.mts`, `implement-prompt.md`, `review-prompt.md`, `pi-models.json` — content being ported into `examples/sequential_reviewer/`
