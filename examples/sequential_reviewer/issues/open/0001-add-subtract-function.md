---
title: Add a subtract function to src/calc.py
labels: [feature]
priority: P2
created: 2026-10-10
---

## Description

Add a `subtract(a: float, b: float) -> float` function to `src/calc.py`,
exported the same way as `add`.

## Acceptance criteria

- `subtract(5, 3)` returns `2`.
- A test for it exists in `tests/test_calc.py`, following the existing
  pattern used for `add`.
