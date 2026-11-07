"""The guard copy check (scripts/guard_copy.py), offline: the canonical files come from
a stand-in for the fetch, and the tracked files from a git repository made in a
temporary directory. `make guard` runs the real check against GitHub."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("guard_copy", ROOT / "scripts" / "guard_copy.py")
assert _spec is not None and _spec.loader is not None
guard_copy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard_copy)

SHA = "a" * 40
CI = f"""jobs:
  checks:
    uses: those-who-run/.github/.github/workflows/checks.yml@{SHA} # v0.2.0
"""
# A skill and a brief as .github would hold them. The braces are there because a
# copy is bytes, whatever a template engine would make of them.
SKILL = b"---\nname: twr-dev\n---\n\nThe loop for one change: {{ not }} [[ a ]] [% template %].\n"
BRIEF = b"---\nname: twr-reviewer\n---\n\nA second read, never an approval.\n"
MANIFEST = {
    "agent/agents/twr-reviewer.md": ".claude/agents/twr-reviewer.md",
    "agent/guard.py": ".claude/hooks/guard.py",
    "agent/settings.json": ".claude/settings.json",
    "agent/skills/twr-dev/SKILL.md": ".claude/skills/twr-dev/SKILL.md",
}


def manifest_bytes(manifest: object) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


class Pin(unittest.TestCase):
    def test_this_repositorys_ci_pins_one_commit(self):
        sha = guard_copy.pinned_commit((ROOT / guard_copy.CI).read_text())
        self.assertRegex(sha, r"^[0-9a-f]{40}$")

    def test_a_tag_is_not_a_pin(self):
        with self.assertRaises(ValueError):
            guard_copy.pinned_commit(CI.replace(SHA, "v0.2.0"))

    def test_two_different_pins_are_refused(self):
        with self.assertRaises(ValueError):
            guard_copy.pinned_commit(CI + CI.replace(SHA, "b" * 40).split("\n", 1)[1])


class Repository(unittest.TestCase):
    """A repository with this repository's guard, settings and config in .claude/, and
    a ci.yml pinned at SHA, where .github holds `self.github`: the guard and the
    settings, and no manifest until a test adds one."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for path in (*guard_copy.COPIES.values(), guard_copy.CONFIG):
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, self.root / path)
        (self.root / guard_copy.CI).parent.mkdir(parents=True)
        (self.root / guard_copy.CI).write_text(CI)
        self.github = {source: (ROOT / copy).read_bytes() for source, copy in guard_copy.COPIES.items()}
        self.asked: list[tuple[str, str]] = []
        # git answers for this directory alone, whatever the caller's environment
        # and configuration say (a commit hook sets GIT_DIR, for one).
        clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        clean.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        env = mock.patch.dict(os.environ, clean, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def canonical(self, commit: str, path: str) -> bytes:
        """What .github holds at `commit`; a 404 for anything else."""
        self.asked.append((commit, path))
        if path not in self.github:
            raise guard_copy.NotFound(f"could not fetch {path} (Not Found)")
        return self.github[path]

    def check(self) -> list[str]:
        return guard_copy.check(self.root, self.canonical)

    def main(self) -> tuple[int, str, str]:
        """main()'s exit status and what it printed, with `self.github` behind
        urlopen: the real fetch, and no network."""

        def urlopen(url: str, **_kwargs):
            path = url.split(f"/{SHA}/", 1)[1]
            if path not in self.github:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO())
            return io.BytesIO(self.github[path])

        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(guard_copy.urllib.request, "urlopen", urlopen):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = guard_copy.main(self.root)
        return status, stdout.getvalue(), stderr.getvalue()

    def write(self, path: str, content: bytes = b"left behind\n") -> None:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_bytes(content)

    def with_manifest(self, manifest: object = MANIFEST) -> None:
        """.github lists the skill and the brief too, and the repository has them."""
        self.github[guard_copy.MANIFEST] = manifest if isinstance(manifest, bytes) else manifest_bytes(manifest)
        self.github["agent/skills/twr-dev/SKILL.md"] = SKILL
        self.github["agent/agents/twr-reviewer.md"] = BRIEF
        self.write(".claude/skills/twr-dev/SKILL.md", SKILL)
        self.write(".claude/agents/twr-reviewer.md", BRIEF)

    def track(self) -> None:
        """Make the repository a git repository that tracks what .claude/ holds now."""
        for args in (["init", "--quiet"], ["add", "--force", "--", ".claude"]):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)


class Copies(Repository):
    """Pinned at a commit of .github from before the manifest: the guard and the
    settings, as the check has always compared them."""

    def test_the_same_files_pass_and_are_fetched_at_the_pin(self):
        self.assertEqual(self.check(), [])
        self.assertEqual(
            sorted(self.asked),
            [(SHA, "agent/copies.json"), (SHA, "agent/guard.py"), (SHA, "agent/settings.json")],
        )

    def test_a_changed_guard_fails(self):
        guard = self.root / ".claude/hooks/guard.py"
        guard.write_bytes(guard.read_bytes() + b"\n# changed\n")
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(".claude/hooks/guard.py is not those-who-run/.github's agent/guard.py", problems[0])

    def test_a_missing_settings_file_fails(self):
        (self.root / ".claude/settings.json").unlink()
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(".claude/settings.json is missing", problems[0])

    def test_a_config_the_guard_cannot_read_fails(self):
        (self.root / ".claude/guard.json").write_text('{"branch": "main", "brnach": "main"}\n')
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn("the guard can't read it", problems[0])

    def test_no_pin_fails_without_fetching(self):
        (self.root / guard_copy.CI).write_text("jobs: {}\n")
        self.assertEqual(len(self.check()), 1)
        self.assertEqual(self.asked, [])

    def test_a_pin_that_is_no_commit_of_github_is_the_fetch_failure(self):
        # Every path is a 404 there, the manifest's first; the guard's says why.
        self.github.clear()
        self.assertEqual(self.check(), ["could not fetch agent/guard.py (Not Found)"])

    def test_a_failed_fetch_is_one_line_not_a_traceback(self):
        def refused(*_args, **_kwargs):
            raise urllib.error.HTTPError("https://example.invalid", 404, "Not Found", {}, io.BytesIO())

        with mock.patch.object(guard_copy.urllib.request, "urlopen", refused):
            with self.assertRaises(guard_copy.FetchError) as raised:
                guard_copy.fetch(SHA, "agent/guard.py")
            message = str(raised.exception)
            self.assertIn(f"raw.githubusercontent.com/those-who-run/.github/{SHA}/agent/guard.py", message)
            self.assertNotIn("\n", message)

            with mock.patch.object(guard_copy, "fetch", side_effect=guard_copy.FetchError(message)):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(guard_copy.main(self.root), 1)
            self.assertEqual(stderr.getvalue(), message + "\n")

    def test_no_network_is_one_line_too(self):
        def offline(*_args, **_kwargs):
            raise urllib.error.URLError(OSError("Name or service not known"))

        with mock.patch.object(guard_copy.urllib.request, "urlopen", offline):
            with self.assertRaises(guard_copy.FetchError) as raised:
                guard_copy.fetch(SHA, "agent/settings.json")
        self.assertIn("Name or service not known", str(raised.exception))
        self.assertNotIsInstance(raised.exception, guard_copy.NotFound)

    def test_only_a_404_says_the_file_is_not_there(self):
        # Any other failure to fetch the manifest must fail the check, not send it
        # to the two guard files as a commit without a manifest does.
        def answer(code: int, reason: str):
            def urlopen(*_args, **_kwargs):
                raise urllib.error.HTTPError("https://example.invalid", code, reason, {}, io.BytesIO())

            return urlopen

        with mock.patch.object(guard_copy.urllib.request, "urlopen", answer(404, "Not Found")):
            with self.assertRaises(guard_copy.NotFound):
                guard_copy.fetch(SHA, "agent/copies.json")
        for code, reason in ((403, "Forbidden"), (429, "Too Many Requests"), (500, "Internal Server Error")):
            with self.subTest(code=code), mock.patch.object(guard_copy.urllib.request, "urlopen", answer(code, reason)):
                with self.assertRaises(guard_copy.FetchError) as raised:
                    guard_copy.fetch(SHA, "agent/copies.json")
                self.assertNotIsInstance(raised.exception, guard_copy.NotFound)

    def test_a_manifest_that_could_not_be_fetched_fails_and_compares_nothing(self):
        def unreachable(commit: str, path: str) -> bytes:
            self.asked.append((commit, path))
            raise guard_copy.FetchError(f"could not fetch {path} (timed out)")

        self.assertEqual(guard_copy.check(self.root, unreachable), ["could not fetch agent/copies.json (timed out)"])
        self.assertEqual(self.asked, [(SHA, "agent/copies.json")])

    def test_it_says_what_it_always_said(self):
        status, stdout, stderr = self.main()
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(
            stdout,
            "the guard and settings in .claude/ are those-who-run/.github's agent/ at the commit "
            ".github/workflows/ci.yml pins\n",
        )


class Manifest(Repository):
    """Pinned at a commit of .github whose agent/copies.json lists a skill and the
    reviewer's brief beside the guard and the settings."""

    def setUp(self):
        super().setUp()
        self.with_manifest()

    def test_every_listed_file_is_fetched_at_the_pin_and_the_same_files_pass(self):
        self.assertEqual(self.check(), [])
        self.assertEqual(sorted(self.asked), sorted((SHA, path) for path in (guard_copy.MANIFEST, *MANIFEST)))

    def test_a_changed_skill_fails(self):
        self.write(".claude/skills/twr-dev/SKILL.md", SKILL + b"One more rule.\n")
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(
            ".claude/skills/twr-dev/SKILL.md is not those-who-run/.github's agent/skills/twr-dev/SKILL.md",
            problems[0],
        )

    def test_a_changed_guard_still_fails(self):
        self.write(".claude/hooks/guard.py", self.github["agent/guard.py"] + b"\n# changed\n")
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(".claude/hooks/guard.py is not those-who-run/.github's agent/guard.py", problems[0])

    def test_a_missing_destination_fails_and_is_named(self):
        (self.root / ".claude/agents/twr-reviewer.md").unlink()
        (self.root / ".claude/settings.json").unlink()
        problems = self.check()
        self.assertEqual(len(problems), 2)
        self.assertIn(".claude/agents/twr-reviewer.md is missing", problems[0])
        self.assertIn("agent/agents/twr-reviewer.md", problems[0])
        self.assertIn(".claude/settings.json is missing", problems[1])

    def test_a_directory_where_a_copy_should_be_fails(self):
        (self.root / ".claude/agents/twr-reviewer.md").unlink()
        (self.root / ".claude/agents/twr-reviewer.md").mkdir()
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn(".claude/agents/twr-reviewer.md is not a file", problems[0])

    def test_a_listed_source_that_github_does_not_have_fails(self):
        del self.github["agent/skills/twr-dev/SKILL.md"]
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn("lists agent/skills/twr-dev/SKILL.md, which is not in those-who-run/.github", problems[0])

    def test_a_config_the_guard_cannot_read_still_fails(self):
        (self.root / ".claude/guard.json").write_text('{"branch": "main", "brnach": "main"}\n')
        problems = self.check()
        self.assertEqual(len(problems), 1)
        self.assertIn("the guard can't read it", problems[0])

    def test_it_says_how_many_files_it_compared(self):
        status, stdout, stderr = self.main()
        self.assertEqual((status, stderr), (0, ""))
        self.assertIn("the 4 files those-who-run/.github's agent/copies.json lists", stdout)

    def test_a_changed_skill_fails_the_command(self):
        self.write(".claude/skills/twr-dev/SKILL.md", SKILL + b"One more rule.\n")
        status, stdout, stderr = self.main()
        self.assertEqual((status, stdout), (1, ""))
        self.assertIn(".claude/skills/twr-dev/SKILL.md is not", stderr)
        self.assertEqual(stderr.count("\n"), 1)


class Stale(Repository):
    """A twr- skill or agent that .github no longer copies, or never did."""

    LEFT_OVER = (
        ".claude/skills/twr-old/SKILL.md",
        ".claude/skills/twr-dev/reference/notes.md",
        ".claude/agents/twr-old.md",
    )
    # A repository's own, by their names, and what the patterns leave alone.
    OWN = (
        ".claude/skills/release-notes/SKILL.md",
        ".claude/agents/reviewer.md",
        ".claude/agents/twr-notes/README.md",
        ".claude/commands/twr-old.md",
    )

    def test_a_tracked_file_the_manifest_does_not_list_fails(self):
        self.with_manifest()
        for path in self.LEFT_OVER:
            self.write(path)
        self.track()
        problems = self.check()
        self.assertEqual(len(problems), len(self.LEFT_OVER))
        for path, problem in zip(sorted(self.LEFT_OVER), problems):
            self.assertTrue(problem.startswith(f"{path} is a stale copy: "), problem)
            self.assertIn("agent/copies.json", problem)
            self.assertIn("Delete it", problem)

    def test_any_such_file_fails_at_a_commit_without_a_manifest(self):
        self.write(".claude/skills/twr-dev/SKILL.md", SKILL)
        self.write(".claude/agents/twr-reviewer.md", BRIEF)
        self.track()
        problems = self.check()
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith(".claude/agents/twr-reviewer.md is a stale copy: "), problems[0])
        self.assertTrue(problems[1].startswith(".claude/skills/twr-dev/SKILL.md is a stale copy: "), problems[1])
        self.assertIn("has no agent/copies.json", problems[0])

    def test_the_repositorys_own_skills_and_agents_pass(self):
        for manifest in (False, True):
            with self.subTest(manifest=manifest):
                if manifest:
                    self.with_manifest()
                for path in self.OWN:
                    self.write(path)
                self.track()
                self.assertEqual(self.check(), [])

    def test_a_file_git_does_not_track_is_not_a_copy(self):
        self.with_manifest()
        self.track()
        self.write(".claude/skills/twr-draft/SKILL.md")
        self.assertEqual(self.check(), [])

    def test_outside_a_git_repository_the_files_on_disk_count(self):
        # A repository just made from the template, or a machine without git: no
        # answer about what is tracked must not read as nothing being stale.
        self.with_manifest()
        self.write(".claude/skills/twr-old/SKILL.md")
        not_a_repository = subprocess.CompletedProcess([], 128, b"", b"fatal: not a git repository")
        for name, run in (
            ("no repository", mock.Mock(return_value=not_a_repository)),
            ("no git", mock.Mock(side_effect=FileNotFoundError("git"))),
        ):
            with self.subTest(name), mock.patch.object(guard_copy.subprocess, "run", run):
                problems = self.check()
                self.assertEqual(len(problems), 1)
                self.assertTrue(problems[0].startswith(".claude/skills/twr-old/SKILL.md is a stale copy: "))
                run.assert_called_once()


class Malformed(Repository):
    """A manifest that can't be trusted fails the check, and nothing is compared
    against it: not a crash, and not a pass."""

    BAD = {
        "not JSON": b"{not json",
        "not UTF-8": b'{"agent/guard.py": "\xff"}',
        "empty": b"",
        "a list": ["agent/guard.py"],
        "a string": "agent/guard.py",
        "nested too deep to read": b"[" * 100_000,
        "a destination that is not a string": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": ["x"]},
        "a destination that is an object": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": {"to": "x"}},
        "a destination outside .claude/": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": "scripts/guard_copy.py"},
        "a destination that only starts like .claude": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": ".claude-x/a"},
        "a destination that is .claude itself": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": ".claude"},
        "a destination that climbs out": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": ".claude/../Makefile"},
        "a destination with .. further in": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": ".claude/skills/../x"},
        "an absolute destination": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": "/.claude/skills/x"},
        "a destination with a backslash": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": ".claude\\skills\\x"},
        "an empty destination": {**MANIFEST, "agent/skills/twr-dev/SKILL.md": ""},
        "a source that climbs out": {**MANIFEST, "agent/../scripts/fan_out.py": ".claude/skills/twr-x/SKILL.md"},
        "an absolute source": {**MANIFEST, "/agent/skills/twr-x/SKILL.md": ".claude/skills/twr-x/SKILL.md"},
        "two sources for one destination": {**MANIFEST, "agent/skills/twr-x/SKILL.md": MANIFEST["agent/guard.py"]},
        "a source listed twice": manifest_bytes(MANIFEST).replace(
            b"{\n", b'{\n  "agent/guard.py": ".claude/skills/twr-x/SKILL.md",\n', 1
        ),
        "no guard": {k: v for k, v in MANIFEST.items() if k != "agent/guard.py"},
        "the guard somewhere else": {**MANIFEST, "agent/guard.py": ".claude/hooks/other.py"},
        "no settings": {k: v for k, v in MANIFEST.items() if k != "agent/settings.json"},
        "nothing at all": {},
    }

    def test_each_fails_and_nothing_is_compared(self):
        for name, manifest in self.BAD.items():
            with self.subTest(name):
                self.asked.clear()
                self.with_manifest(manifest)
                problems = self.check()
                self.assertTrue(problems, "the check passed")
                for problem in problems:
                    self.assertTrue(problem.startswith("those-who-run/.github's agent/copies.json at "), problem)
                    self.assertNotIn("\n", problem)
                self.assertEqual(self.asked, [(SHA, "agent/copies.json")])

    def test_the_message_says_what_is_wrong(self):
        for name, wording in (
            ("not JSON", "is not JSON"),
            ("a list", "is not a JSON object"),
            ("a destination outside .claude/", "sends agent/skills/twr-dev/SKILL.md to scripts/guard_copy.py, outside .claude/"),
            ("a destination that climbs out", "'.claude/../Makefile', which is not a plain relative path"),
            ("a source that climbs out", "the source 'agent/../scripts/fan_out.py'"),
            ("a source listed twice", "lists 'agent/guard.py' twice"),
            ("no guard", "does not send agent/guard.py to .claude/hooks/guard.py"),
        ):
            with self.subTest(name):
                self.with_manifest(self.BAD[name])
                self.assertIn(wording, self.check()[0])

    def test_the_command_prints_it_and_fails(self):
        self.with_manifest(self.BAD["a destination that climbs out"])
        status, stdout, stderr = self.main()
        self.assertEqual((status, stdout), (1, ""))
        self.assertIn("is not a plain relative path", stderr)
        self.assertEqual(stderr.count("\n"), 1)


class ThisRepositorysConfig(unittest.TestCase):
    """This repository's own values in .claude/guard.json."""

    def test_the_guard_config_values(self):
        config = json.loads((ROOT / guard_copy.CONFIG).read_text(encoding="utf-8"))
        self.assertEqual(
            config,
            {
                "branch": "main",
                "release_tags": ["v*"],
                "release_workflow": "release.yml",
                "owner": "those-who-run",
            },
        )


if __name__ == "__main__":
    unittest.main()
