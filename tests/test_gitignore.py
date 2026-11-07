""".gitignore and .claude/: what git would track there, and what it leaves out.

The files those-who-run/.github copies into every repository (the guard, the
settings, the skills and the agents' briefs) must be trackable, or the copy check
(scripts/guard_copy.py) compares files a clone doesn't have; a session's own files
there, the worktrees among them, must stay out. Each case puts files in a new git
repository that has this repository's .gitignore, adds everything, and reads back
what git took, so it holds whatever the caller's own git configuration ignores.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TRACKED = {
    ".claude/settings.json",
    ".claude/guard.json",
    ".claude/hooks/guard.py",
    ".claude/skills/twr-dev/SKILL.md",
    ".claude/skills/twr-dev/reference/notes.md",
    ".claude/agents/twr-reviewer.md",
}
IGNORED = {
    ".claude/settings.local.json",
    ".claude/worktrees/i1/README.md",
    # A worktree is a checkout, with copies of its own.
    ".claude/worktrees/i1/.claude/skills/twr-dev/SKILL.md",
    ".claude/worktrees/i1/.claude/agents/twr-reviewer.md",
    ".claude/hooks/other.py",
    ".claude/hooks/__pycache__/guard.cpython-315.pyc",
    ".claude/scheduled_tasks.lock",
    ".claude/plans/next.md",
}


class Gitignore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.repo = Path(cls._tmp.name)
        shutil.copyfile(ROOT / ".gitignore", cls.repo / ".gitignore")
        for path in TRACKED | IGNORED:
            (cls.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (cls.repo / path).write_text("x\n")
        # This repository's .gitignore alone: no GIT_DIR from a commit hook, no
        # configuration of the caller's, and no excludes file of theirs.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        cls.env = env
        cls.git("init", "--quiet")
        cls.git("add", "--all")
        cls.tracked = {f for f in cls.git("ls-files", "-z").split("\0") if f}

    @classmethod
    def git(cls, *args: str) -> str:
        done = subprocess.run(
            ["git", "-c", f"core.excludesFile={os.devnull}", *args],
            cwd=cls.repo, env=cls.env, capture_output=True, text=True, check=False,
        )
        if done.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}:\n{done.stdout}{done.stderr}")
        return done.stdout

    def test_the_copies_are_tracked(self):
        self.assertEqual(TRACKED - self.tracked, set(), "git left these out")

    def test_the_rest_of_dot_claude_stays_out(self):
        self.assertEqual(IGNORED & self.tracked, set(), "git took these")

    def test_git_names_the_rule_that_leaves_each_out(self):
        # `git check-ignore -v`: the pattern that decides. For a worktree's files it
        # is `.claude/*`, on the worktrees directory itself.
        for path in sorted(IGNORED):
            with self.subTest(path=path):
                source, _, _ = self.git("check-ignore", "-v", "--no-index", "--", path).partition("\t")
                self.assertRegex(source, r"^\.gitignore:\d+:\.claude/(hooks/)?\*$")


if __name__ == "__main__":
    unittest.main()
