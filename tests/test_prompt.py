"""Unit tests for the prompt pipeline. No Docker required — shell-expansion
is tested against a tiny local-subprocess fake sandbox handle, since the
logic under test is the regex/substitution pipeline, not Docker itself."""

from __future__ import annotations

import subprocess

import pytest

from sandcastle.errors import PromptError, ShellExpansionError
from sandcastle.prompt import (
    detect_completion_signal,
    expand_shell_expressions,
    substitute_prompt_args,
)
from sandcastle.types import ExecResult


class FakeLocalSandbox:
    """Runs shell commands on the host — enough to test expansion ordering
    and replacement without needing a real sandbox."""

    def exec(self, command, *, cwd=None, timeout_seconds=None, **_):
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ExecResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def test_substitute_basic_key():
    result = substitute_prompt_args(
        "Work on issue {{ISSUE_NUMBER}}.",
        {"ISSUE_NUMBER": "42"},
        source_branch="src",
        target_branch="tgt",
    )
    assert result == "Work on issue 42."


def test_substitute_builtins_injected():
    result = substitute_prompt_args(
        "{{SOURCE_BRANCH}} -> {{TARGET_BRANCH}}",
        {},
        source_branch="feature/x",
        target_branch="main",
    )
    assert result == "feature/x -> main"


def test_substitute_rejects_builtin_override():
    with pytest.raises(PromptError):
        substitute_prompt_args(
            "{{SOURCE_BRANCH}}",
            {"SOURCE_BRANCH": "evil"},
            source_branch="feature/x",
            target_branch="main",
        )


def test_substitute_missing_key_errors():
    with pytest.raises(PromptError):
        substitute_prompt_args("{{UNDEFINED}}", {}, source_branch="s", target_branch="t")


def test_substitute_unused_arg_warns():
    with pytest.warns(UserWarning):
        result = substitute_prompt_args(
            "no placeholders here", {"UNUSED": "x"}, source_branch="s", target_branch="t"
        )
    assert result == "no placeholders here"


def test_substitute_applies_inside_shell_blocks():
    # {{KEY}} substitution must apply even inside `` !`cmd` `` text — the
    # shell command hasn't run yet at this point in the pipeline.
    result = substitute_prompt_args(
        "!`echo {{ISSUE_NUMBER}}`", {"ISSUE_NUMBER": "7"}, source_branch="s", target_branch="t"
    )
    assert result == "!`echo 7`"


def test_expand_shell_expressions_replaces_stdout():
    result = expand_shell_expressions("before !`echo hi` after", FakeLocalSandbox())
    assert result == "before hi after"


def test_expand_shell_expressions_multiple_in_order():
    result = expand_shell_expressions("!`echo a`-!`echo b`-!`echo c`", FakeLocalSandbox())
    assert result == "a-b-c"


def test_expand_shell_expressions_no_matches_is_noop():
    result = expand_shell_expressions("nothing to expand", FakeLocalSandbox())
    assert result == "nothing to expand"


def test_expand_shell_expressions_failure_raises():
    with pytest.raises(ShellExpansionError):
        expand_shell_expressions("!`exit 1`", FakeLocalSandbox())


def test_detect_completion_signal_found():
    assert detect_completion_signal("...<promise>COMPLETE</promise>", ("<promise>COMPLETE</promise>",)) == (
        "<promise>COMPLETE</promise>"
    )


def test_detect_completion_signal_not_found():
    assert detect_completion_signal("still working", ("<promise>COMPLETE</promise>",)) is None
