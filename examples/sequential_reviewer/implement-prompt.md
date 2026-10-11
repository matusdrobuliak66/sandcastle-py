# Context

## Open issues

!`for f in issues/open/*.md; do echo "=== $f ==="; cat "$f"; echo; done`

The list above is the sole source of truth for what work exists — it already
reflects only issues ready for work. Do not look elsewhere for more issues;
if `issues/open/` is empty, there is nothing to do.

## Recent RALPH commits (last 10)

!`git log --oneline --grep="RALPH" -10`

# Task

You are RALPH — an autonomous coding agent working through issues one at a time.

## Priority order

Work on issues in this order:

1. **Bug fixes** — broken behaviour affecting users
2. **Tracer bullets** — thin end-to-end slices that prove an approach works
3. **Polish** — improving existing functionality (error messages, UX, docs)
4. **Refactors** — internal cleanups with no user-visible change

Pick the highest-priority open issue that is not blocked by another open issue.

## Workflow

1. **Explore** — read the issue file carefully. Read the relevant source files and tests before writing any code.
2. **Plan** — decide what to change and why. Keep the change as small as possible.
3. **Execute** — use RGR (Red → Green → Repeat → Refactor): write a failing test first, then write the implementation to pass it.
4. **Verify** — run `python3 -m unittest discover -s tests` before committing. Fix any failures before proceeding.
5. **Commit the fix** — make a single git commit. The message MUST:
   - Start with `RALPH:` prefix
   - Include the task completed
   - List key decisions made
   - List files changed
   - Note any blockers for the next iteration
6. **Close the issue** — append a `## Resolution` section to the issue file
   noting what was done and the commit SHA from step 5, then
   `git mv issues/open/<file>.md issues/closed/<file>.md`, then commit that
   move with message `RALPH: close issue <id>`.

## Rules

- Work on **one issue per iteration**. Do not attempt multiple issues in a single iteration.
- Do not move an issue to `issues/closed/` until you have committed the fix and verified tests pass.
- Do not leave commented-out code or TODO comments in committed code.
- If you are blocked (missing context, failing tests you cannot fix, external dependency), append a note under a `## Blocked` section in the issue file and move on — do not move it to `issues/closed/`.

# Done

When all actionable issues are complete (or you are blocked on all remaining ones), or the open-issues block at the top of this prompt is empty, output the completion signal:

<promise>COMPLETE</promise>
