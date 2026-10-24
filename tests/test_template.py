"""The template: copier.yml and the .jinja files, rendered as a new repository would
be, with and without an image.

Each case renders this working tree (``--vcs-ref HEAD``, which takes uncommitted
changes too) into a temporary directory with copier, installed from
.github/requirements-copier.txt into build/copier-venv. It checks that the rendered
repository has every file chassis has, each the same as chassis's own but for the
repository's name, and then runs the rendered repository's own checks there: gofmt,
`go mod tidy`, go vet, go build and `make test` (the Go tests with the coverage
floor, the links, the guard copy and its tests). So a template change that breaks
a new repository fails `make test` and CI's `test` job.

It needs Go, python3 and the network (copier's install, the guard copy check).
This file stays in chassis (copier.yml's _exclude).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / ".github" / "requirements-copier.txt"
VENV = ROOT / "build" / "copier-venv"
# A name that appears nowhere in chassis, so every place it lands in a rendered file
# is where chassis's own name was.
NAME = "testcar"
DESCRIPTION = "The test car: what tests/test_template.py renders."

# In chassis, never in a repository made from it.
CHASSIS_ONLY = {
    "copier.yml",
    ".github/requirements-copier.txt",
    "tests/test_template.py",
}
IMAGE_FILES = {
    "Dockerfile",
    ".dockerignore",
    ".github/workflows/image.yml",
    ".github/workflows/release.yml",
}
# Files whose rendering is more than chassis's own with the name changed.
README = "README.md"
ANSWERS = ".copier-answers.yml"
RELEASE = ".github/workflows/release.yml"
RELEASE_PR = ".github/workflows/release-pr.yml"
CHASSIS_ONLY_CONDITION = (
    "    # chassis is the template, not a component: it never publishes an image.\n"
    "    if: github.repository != 'those-who-run/chassis'\n"
)


def copier() -> Path:
    """copier at the pinned version, installed into build/copier-venv once per
    version of the requirements file."""
    stamp = VENV / "installed"
    want = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if not stamp.is_file() or stamp.read_text() != want:
        shutil.rmtree(VENV, ignore_errors=True)
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
        subprocess.run(
            [str(VENV / "bin" / "python"), "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", "--require-hashes", "-r", str(REQUIREMENTS)],
            check=True,
        )
        stamp.write_text(want)
    return VENV / "bin" / "copier"


def chassis_files() -> set[str]:
    """chassis's files, tracked or new, but not ignored: what copier copies from."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    return {f for f in out.split("\0") if f and (ROOT / f).is_file()}


def files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def as_rendered(path: str) -> str:
    """Where a file of chassis lands in the rendered repository."""
    return path.replace("cmd/chassis/", f"cmd/{NAME}/", 1)


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


class Rendered(unittest.TestCase):
    """A repository rendered from the template with IMAGE as the answer."""

    IMAGE = True

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dst = Path(cls._tmp.name) / NAME
        cmd = [
            str(copier()), "copy", "--defaults", "--quiet", "--vcs-ref", "HEAD",
            "--data", f"name={NAME}", "--data", f"description={DESCRIPTION}",
            "--data", f"image={str(cls.IMAGE).lower()}",
            str(ROOT), str(cls.dst),
        ]
        done = run(cmd, ROOT)
        if done.returncode != 0:
            cls._tmp.cleanup()
            raise AssertionError(f"copier copy failed:\n{done.stdout}{done.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def rendered(self, path: str) -> str:
        return (self.dst / path).read_text(encoding="utf-8")

    def expected_files(self) -> set[str]:
        want = {
            as_rendered(f)
            for f in chassis_files()
            if f not in CHASSIS_ONLY and not f.endswith(".jinja")
        }
        if not self.IMAGE:
            want -= IMAGE_FILES
        return want | {ANSWERS}

    def test_every_file_of_chassis_and_nothing_else(self):
        self.assertEqual(files(self.dst), self.expected_files())

    def test_each_file_is_chassiss_own_with_the_name_changed(self):
        for path in sorted(self.expected_files() - {README, ANSWERS}):
            with self.subTest(path=path):
                want = (ROOT / path.replace(f"cmd/{NAME}/", "cmd/chassis/", 1)).read_text(
                    encoding="utf-8"
                )
                if path == RELEASE:
                    self.assertIn(CHASSIS_ONLY_CONDITION, want)
                    want = want.replace(CHASSIS_ONLY_CONDITION, "")
                if path == RELEASE_PR and not self.IMAGE:
                    want = want.replace("release-workflow: release.yml", 'release-workflow: ""')
                self.assertEqual(self.rendered(path).replace(NAME, "chassis"), want)

    def test_only_the_readme_and_the_answers_name_chassis(self):
        naming = {f for f in files(self.dst) if "chassis" in self.rendered(f)}
        self.assertEqual(naming, {README, ANSWERS})

    def test_every_template_renders_in_place_of_chassiss_own_file(self):
        # A .jinja file without a plain sibling would leave chassis without the file
        # it gives a new repository, so `make check` here would not cover it.
        for path in sorted(f for f in chassis_files() if f.endswith(".jinja")):
            if path.startswith("[[_copier_conf.answers_file]]") or path == "README.md.jinja":
                continue
            plain = path.removesuffix(".jinja").replace("cmd/[[name]]/", "cmd/chassis/", 1)
            with self.subTest(path=path):
                self.assertIn(plain, chassis_files())

    def test_the_readme(self):
        readme = self.rendered(README)
        self.assertTrue(readme.startswith(f"# Testcar\n\n{DESCRIPTION}\n\n"), readme[:200])
        self.assertIn("## Conventions", readme)
        image = f"ghcr.io/those-who-run/twr-{NAME}:X.Y.Z"
        if self.IMAGE:
            self.assertIn(image, readme.replace("\n", " "))
        else:
            self.assertNotIn(image, readme.replace("\n", " "))
            self.assertIn("It ships\nno image.", readme)

    def test_the_answers_let_copier_update_find_the_template(self):
        answers = self.rendered(ANSWERS)
        for line in (f"name: {NAME}", f"image: {str(self.IMAGE).lower()}", "_src_path: ", "_commit: "):
            self.assertIn(line, answers)

    def test_the_rendered_repository_passes_its_checks(self):
        targets = ["fmt-check", "tidy", "vet", "build", "test"] if self.IMAGE else ["vet", "build"]
        done = run(["make", *targets], self.dst)
        self.assertEqual(done.returncode, 0, f"make {' '.join(targets)}:\n{done.stdout}{done.stderr}")


class RenderedWithoutAnImage(Rendered):
    """A library's repository: no Dockerfile, no image check and nothing to publish.
    Its checks run as the one above, so here only vet and build run, to show the
    Go code still builds."""

    IMAGE = False

    def test_no_release_workflow_is_dispatched(self):
        self.assertIn('release-workflow: ""', self.rendered(RELEASE_PR))


if __name__ == "__main__":
    unittest.main()
