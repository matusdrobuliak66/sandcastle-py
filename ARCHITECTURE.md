# Architecture

This document explains *why* sandcastle-py is built the way it is — the
decisions, the rejected alternatives, and the things that look unusual
until you know the reasoning. `PLAN.md` tracks build *status* (what's done,
what's left); this file is the stable reference for *design*. Load this
one when you come back to extend or modify the project.

## What this is

A minimal Python orchestrator that runs the `pi` coding-agent CLI inside a
Docker sandbox, driven by a self-hosted vLLM model, with a local
file-based issue tracker instead of GitHub. It's a deliberately narrow
reimplementation of one real-world tool, `@ai-hero/sandcastle` (a
Node/TS library) — see "Relationship to the original" below for how
closely each piece was ported versus redesigned.

The motivating use case: run an autonomous implement→review loop
*unattended, possibly overnight*, against a local model. That constraint
— nobody watching it — is why the network lockdown exists and why the
issue tracker has no live network dependency at all.

## The three abstractions, and why they exist with only one implementation each

`AgentProvider`, `SandboxProvider`, and `BranchStrategy` are real
`Protocol`/`ABC` classes in `src/sandcastle/protocols/`, even though v1
ships exactly one concrete implementation of each (`PiAgentProvider`,
`DockerSandboxProvider`, `LocalBranchStrategy`). This was an explicit
requirement, not speculative design: the point is that adding a second
agent CLI, a Podman sandbox, or a merge-to-head branch strategy later
should mean writing a new class against an existing contract, not
reshaping the core. The original JS library has exactly this shape with
six agent providers and three sandbox providers; we only ever need one of
each, but the *shape* that let the JS version grow that way is worth
keeping.

Two unimplemented branch strategies (`HeadBranchStrategy`,
`MergeToHeadBranchStrategy`) are typed stubs that raise
`NotImplementedError` with a message describing what they'd do. They exist
purely so the dispatch shape is already right if you need them — don't
delete them thinking they're dead code, and don't feel obligated to
implement them until you actually need no-worktree or auto-merge behavior.

## Why Docker via `subprocess`, not `docker-py`

`DockerSandboxProvider` shells out to the `docker` CLI directly
(`subprocess.run`/`Popen`) instead of using the `docker` Python package or
talking to the Engine API socket. This mirrors the real JS sandcastle
exactly (confirmed by reading its compiled source) and was a deliberate
zero-dependency choice: every operation in `sandboxes/docker.py` is a
`docker` command you could type yourself and debug by hand — `docker run`,
`docker exec`, `docker cp`, `docker stop`/`rm`. No socket permissions to
reason about, no SDK version to track against your Docker version, and
the whole project has **zero runtime dependencies** as a result (see
`pyproject.toml` — `dependencies = []`).

The `exec()` method has two modes: a simple blocking `subprocess.run()`
when no `on_line` callback is given, and a `Popen` + background-thread
version when one is (used by the agent-output streaming path, so you see
output live rather than only after the whole command finishes).

A module-level registry (`_active_containers`) plus an `atexit` hook and a
`SIGTERM` handler force-removes any container left running if the process
exits without a clean `handle.close()` — this is a direct port of the JS
version's same safety net. Without it, a crashed script leaves `docker ps
-a` cluttered with dead sandboxes indefinitely.

## Why network lockdown exists, and why it's iptables + `NET_ADMIN`

**The problem**: this is meant to run unattended, with the agent having
full shell access inside the container. Docker's default bridge network
gives a container unrestricted outbound access — to anything. Combined
with an agent that has `bash` and no one watching, that's a real
exfiltration/supply-chain risk, not a theoretical one.

**The constraint that shaped the design**: the agent still needs to reach
*something* — the self-hosted model endpoint — so "no network at all"
(`--network none`) isn't viable. The requirement became: reach exactly
one IP:port, nothing else.

**What we actually do** (`sandboxes/network_lockdown.py` +
`DockerSandboxProvider.create()`):

1. Start the container with `--cap-add=NET_ADMIN` — but *only* when a
   lockdown is configured; a sandbox with no `network_lockdown` doesn't
   get the extra capability at all.
2. Immediately after the container starts, before any hook or agent
   process runs, issue one root-level `docker exec --user 0:0` that
   installs three `iptables` rules: allow loopback, allow TCP to the one
   configured IP:port, then set the default `OUTPUT` policy to `DROP`.
   Order matters — the allow-rules must land *before* the deny-everything
   policy, or there's a window where the container is simply offline.
3. Every other `docker exec` call — every hook, the agent process itself —
   runs with `--user <uid>:<gid>` (the unprivileged `agent` user), never
   as root. That user cannot re-run `iptables` to reopen the firewall
   without first regaining root through some unrelated privilege-escalation
   bug — which is a materially different, much narrower risk than "the
   agent has root."

**Why a raw IP, not a hostname**: `NetworkLockdown.__post_init__` calls
`ipaddress.ip_address(self.allow_host)` and raises if it isn't a valid IP.
This is enforced, not just documented, because DNS lookups are blocked by
the same default-deny policy — a hostname here would silently never
resolve, and you'd get a confusing timeout instead of a clear error at
construction time.

**Alternatives considered and rejected** (don't re-litigate these without
new information):

- *Proxy-sidecar container on an `internal: true` Docker network.* This
  was the originally-proposed approach for the *existing* JS/Node setup,
  before this Python rewrite. Rejected here because it only actually
  closes the hole if the sandboxed container is *also* blocked from
  routing around the sidecar — which means it still needs this same
  in-container iptables mechanism, plus a second container with its own
  lifecycle and failure modes. Strictly more complexity for the same
  guarantee.
- *Host-level macOS firewall rule.* Docker Desktop runs containers inside
  a Linux VM; a host-level rule acts on that VM's network stack as a
  whole, with no visibility into which *container* a connection belongs
  to. It can only express "block for all Docker traffic on this machine,"
  which breaks every other container too. Rejected.
- *`pi --offline`.* This flag only suppresses `pi`'s own self-update HTTP
  check at startup. It has zero effect on what the agent's tool calls
  (`bash`, `curl`, `git fetch`, ...) can reach. Not a sandboxing control —
  don't present it as one.

**How this is tested**: `tests/test_network_lockdown.py` deliberately does
*not* depend on the live external vLLM endpoint. The "allowed" target is a
second local container (`python3 -m http.server`) on the same Docker
bridge network, with its IP discovered via `docker inspect`. This makes
the test deterministic and runnable with no dependency on infrastructure
outside the dev machine — which turned out to matter in practice: the
real vLLM endpoint went unreachable partway through this project (an
infra issue, confirmed by `curl` failing from the host directly, not a
bug in the lockdown), and the test suite was unaffected.

## The `pi` agent provider: stdin, not `@file`

`PiAgentProvider.build_print_command()` pipes the resolved prompt to `pi`
via stdin (`echo "<prompt>" | pi -p --mode json --model ...`). This was
empirically determined, not assumed: `pi -p --mode json ... @promptfile`
with no additional positional message **hangs** — it appears to wait for
an explicit message string in addition to the `@file` attachment, which is
documented for attaching *extra* files (`pi @prompt.md @image.png "..."`),
not for delivering the entire prompt. Piping via stdin works and matches
what the real JS sandcastle's `pi` provider actually does
(`stdin: prompt`). If you're ever tempted to "simplify" this to `@file`
delivery because it looks cleaner, don't, without re-testing against a
live model first.

`parse_stream_line()` is built against the actual `--mode json` event
schema captured from a live run (not guessed from `pi --help`). The
top-level event types that matter: `session` (carries the session id),
`message_update` with `assistantMessageEvent.type == "text_delta"` (the
assistant's streamed text), `tool_execution_start`/`tool_execution_end`
(a tool call and its result — this is how you'd observe `bash`/`edit`/
`write` calls during a real implement run). Everything else
(`thinking_*`, `toolcall_*` streaming deltas, `turn_start`/`turn_end`,
`agent_start`/`agent_end`) is intentionally ignored, not fatal — unknown
or uninteresting event shapes should never crash the parser.

## Branch strategy: why "local branch, no merge, no push" and nothing else

`LocalBranchStrategy` creates a git worktree on a new named branch and,
when finalizing, only *reads* commits via `git rev-list` — it never
merges, never pushes, never deletes the branch. This is the lowest-blast-
radius option by construction: a bad autonomous run leaves an orphaned
local branch for you to inspect, not a modified `main` and not a push to
a remote anyone else can see. This was a deliberate choice carried over
from validating the equivalent JS setup first — `head` and `merge-to-head`
are real strategies in the original with real use cases, but "something
is going to run unattended and I'm not 100% sure what it'll do" is
specifically the scenario this strategy is for.

Commit collection runs `git rev-list <base_head>..refs/heads/<branch>
--reverse` against the **host repo directory**, not the worktree path.
This isn't a shortcut — worktrees share the same object database and refs
as the main repo, so the main repo dir can already see the branch's new
commits once they exist, regardless of which worktree (if any) currently
has that branch checked out. Don't "fix" this to point at the worktree
path; it would still work by accident most of the time but it's not the
actually-correct reason it works.

## Prompt pipeline: ordering is the whole point

Two passes, strict order:

1. `{{KEY}}` substitution — host-side, before the sandbox is touched.
   Built-in `SOURCE_BRANCH`/`TARGET_BRANCH` are injected automatically and
   cannot be overridden (raises `PromptError` if you try). This pass runs
   across the *entire* template, including inside `` !`cmd` `` blocks —
   that's intentional (`` !`cat issues/{{ISSUE_ID}}.md` `` should work),
   not a bug to guard against. There's no double-substitution risk because
   each regex runs exactly once and shell commands haven't executed yet
   when this pass happens.
2. `` !`command` `` shell-expansion — sandbox-side, and critically, re-run
   **fresh on every iteration** of a multi-iteration run, not once per
   `Sandbox.run()` call. See "stateless iterations" below for why that
   matters.

Shell-expansion commands run concurrently (`ThreadPoolExecutor`), each
with its own timeout (30s default), and a non-zero exit from any one of
them is a hard error for the whole prompt resolution — a flaky `` !`cmd`
`` shouldn't silently produce a prompt missing half its context.

## Stateless iterations: the memory model

Each iteration of `Sandbox.run(max_iterations=N)` spawns a **brand-new
`pi` process with no conversational memory of the previous iteration**.
The repo (and, for the example, the `issues/` directory) is the only thing
that persists between iterations — which is exactly why shell-expansion
has to re-run every iteration rather than once: `` !`for f in
issues/open/*.md; do cat "$f"; done` `` needs to see whatever the *previous*
iteration just moved into `issues/closed/`. If you ever add a feature
that caches the expanded prompt across iterations, you will quietly break
the entire reason RALPH-style loops work.

## The local issue tracker: deliberately no code

`issues/open/*.md` / `issues/closed/*.md`, plain YAML-frontmatter markdown
files. There is **no tracker module in this library** — the agent reads,
writes, and `git mv`s these files using its own `read`/`write`/`edit`/
`bash` tools, driven entirely by instructions in `implement-prompt.md`.
This wasn't laziness: adding a parser for a data shape the library itself
never needs to understand would be exactly the kind of premature
abstraction this project is trying to avoid. The *only* place the schema
is defined is in prose, in the prompt. If you add real tracker logic
later (search, bulk operations, a CLI), keep it a separate tool that
operates on the same files — don't pull parsing into `sandcastle` itself
unless the library needs to act on the data, not just have the agent read
it.

## A config-drift lesson, baked into `examples/sequential_reviewer/main.py`

Early on, the model endpoint's IP changed mid-session, and two separate
config files (the host's `pi` config and the sandbox's copy) had to be
updated by hand and briefly drifted out of sync. `main.py` avoids
repeating that: it reads `pi-models.json`'s `baseUrl` at startup and
derives the `NetworkLockdown`'s allowed host/port from it directly
(`_network_lockdown_from_pi_models_json`), rather than hardcoding the
IP a second time in Python. If the model moves, you only ever edit one
file.

## Known v1 simplifications (not oversights — just not needed yet)

- **Hooks run sequentially**, not concurrently (host hooks, then sandbox
  hooks). The original runs them in parallel; for the handful of setup
  commands these templates use (`npm install`/`pip install`-equivalent,
  copying one config file), the time difference is negligible against the
  complexity of getting concurrent hook failure-handling right.
- **Mount-directory prep chowns only the top-level path**, not
  recursively, and only matters at all if you pass extra `mounts=[...]`
  to `DockerSandboxProvider` — the shipped example doesn't use that, only
  `copy_to_worktree`. Revisit if `mounts` gets real use.
- **`env_file.py` exists but isn't wired into anything yet** — no `.env`-
  consuming code path exists in the current example. It's a hand-rolled
  ~20-line parser (no `python-dotenv` dependency, matching the original's
  own choice not to pull in `dotenv` either), ready whenever something
  needs it.
- **No session resume/fork, no structured output extraction, no retries.**
  All real features of the original JS library, all deliberately out of
  scope for a single-agent, single-model, locally-run tool. If you add
  them, port the *behavior* (e.g. "only iteration 1 of a multi-iteration
  run can resume; later ones always start fresh" for resume) rather than
  re-deriving it from scratch.

## Relationship to the original (`@ai-hero/sandcastle`)

This is not a 1:1 port. Ported faithfully: the three-abstraction shape,
the `docker` CLI subprocess approach, the prompt substitution/expansion
ordering, the stateless-iteration model, the "branch" strategy's
no-merge/no-push semantics, the commit-collection mechanism. Deliberately
redesigned or dropped: GitHub issue tracking (replaced with local files),
five of six agent providers, two of three sandbox providers, two of three
branch strategies (kept as stubs), session resume/fork/retries/structured
output, and — the one genuinely new piece with no JS equivalent — the
network lockdown, which exists because this project's whole point is
running unattended with a locally-hosted model, a scenario the original
library was never specifically designed around.
