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

# In chassis, never in a repository made from it. CHANGELOG.md is chassis's release
# history, once release-please has written one.
CHASSIS_ONLY = {
    "copier.yml",
    ".github/requirements-copier.txt",
    "tests/test_template.py",
    "CHANGELOG.md",
}
IMAGE_FILES = {
    "Dockerfile",
    ".dockerignore",
    ".github/workflows/image.yml",
    ".github/workflows/release.yml",
}
# A library has no example service: no cmd/ and no internal/service/. It gets a
# placeholder package instead, which chassis, a service, has only as templates
# whose names render empty with an image.
SERVICE_DIRS = ("cmd/", "internal/service/")
LIBRARY_FILES = {"doc.go", "doc_test.go"}
LIBRARY_ONLY_PREFIX = "[% if not image %]"
# Files whose rendering is more than chassis's own with the name changed.
README = "README.md"
ANSWERS = ".copier-answers.yml"
RELEASE = ".github/workflows/release.yml"
RELEASE_PR = ".github/workflows/release-pr.yml"
# A repository's own release-please manifest, which starts at 0.0.0 whatever chassis
# has released.
MANIFEST = ".release-please-manifest.json"
FIRST_MANIFEST = '{".": "0.0.0"}\n'
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


def copier_copy(src: Path, dst: Path, image: bool, *extra: str, name: str = NAME) -> None:
    """Render src into dst with the test answers, or fail with copier's output."""
    cmd = [
        str(copier()), "copy", "--defaults", "--quiet", *extra,
        "--data", f"name={name}", "--data", f"description={DESCRIPTION}",
        "--data", f"image={str(image).lower()}",
        str(src), str(dst),
    ]
    done = run(cmd, ROOT)
    if done.returncode != 0:
        raise AssertionError(f"copier copy failed:\n{done.stdout}{done.stderr}")


class Rendered(unittest.TestCase):
    """A repository rendered from the template with IMAGE as the answer."""

    IMAGE = True

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.dst = Path(cls._tmp.name) / NAME
        try:
            copier_copy(ROOT, cls.dst, cls.IMAGE, "--vcs-ref", "HEAD")
        except AssertionError:
            cls._tmp.cleanup()
            raise

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
            want = {f for f in want if not f.startswith(SERVICE_DIRS)} | LIBRARY_FILES
        return want | {ANSWERS}

    def test_every_file_of_chassis_and_nothing_else(self):
        self.assertEqual(files(self.dst), self.expected_files())

    def test_each_file_is_chassiss_own_with_the_name_changed(self):
        for path in sorted(self.expected_files() - {README, ANSWERS} - LIBRARY_FILES):
            with self.subTest(path=path):
                if path == MANIFEST:
                    self.assertEqual(self.rendered(path), FIRST_MANIFEST)
                    continue
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
        # A library's own files have no sibling here, chassis being a service; the
        # render without an image runs every check on them instead.
        for path in sorted(f for f in chassis_files() if f.endswith(".jinja")):
            if path.startswith(("[[_copier_conf.answers_file]]", LIBRARY_ONLY_PREFIX)):
                continue
            if path == "README.md.jinja":
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

    def test_the_service_is_there_only_with_an_image(self):
        for directory in ("cmd", "internal/service"):
            # The directory itself too, not only its files.
            with self.subTest(directory=directory):
                self.assertEqual((self.dst / directory).is_dir(), self.IMAGE)
        self.assertEqual((self.dst / "doc.go").is_file(), not self.IMAGE)

    def test_the_rendered_repository_passes_its_checks(self):
        # make check's Go checks and make test; only the commit hooks are left out,
        # since the render is no git repository.
        targets = ["fmt-check", "tidy", "vet", "lint", "build", "test", "vuln"]
        done = run(["make", *targets], self.dst)
        self.assertEqual(done.returncode, 0, f"make {' '.join(targets)}:\n{done.stdout}{done.stderr}")


class RenderedWithoutAnImage(Rendered):
    """A library's repository: no Dockerfile, no image check, nothing to publish and
    no example service, but a placeholder package that every check runs on."""

    IMAGE = False

    def test_the_placeholder_package(self):
        doc = self.rendered("doc.go")
        self.assertIn(f"// Package {NAME} is the {NAME} library", doc)
        self.assertIn(f'func Name() string {{ return "{NAME}" }}', doc)
        test = self.rendered("doc_test.go")
        self.assertIn(f'"github.com/those-who-run/{NAME}"', test)
        self.assertIn(f"// Output: {NAME}", test)

    def test_a_hyphenated_name_still_makes_a_package(self):
        # A Go package name has no hyphens; the module path keeps them.
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "test-car"
            copier_copy(ROOT, dst, False, "--vcs-ref", "HEAD", name="test-car")
            self.assertIn("package testcar\n", (dst / "doc.go").read_text(encoding="utf-8"))
            done = run(["make", "vet", "go-test"], dst)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_no_release_workflow_is_dispatched(self):
        self.assertIn('release-workflow: ""', self.rendered(RELEASE_PR))

    def test_release_please_still_gets_what_its_jobs_ask_for(self):
        # GitHub refuses to start a reusable workflow whose jobs ask for more than
        # the caller grants, even jobs that would be skipped, so the dispatch's
        # permission stays with no release workflow to dispatch.
        self.assertIn("      actions: write\n", self.rendered(RELEASE_PR))


class ChassisReleaseHistoryStaysInChassis(unittest.TestCase):
    """Once chassis has released, its version and changelog are still its own: a
    scratch copy of chassis with both, rendered, gives a repository at 0.0.0 with no
    changelog, and a render over a repository that has released keeps its version."""

    CHASSIS_VERSION = "4.5.6"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.src = tmp / "chassis"
        for f in chassis_files():
            (cls.src / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, cls.src / f)
        (cls.src / MANIFEST).write_text(f'{{".": "{cls.CHASSIS_VERSION}"}}\n', encoding="utf-8")
        (cls.src / "CHANGELOG.md").write_text(
            "# Changelog\n\n"
            f"## [{cls.CHASSIS_VERSION}](https://github.com/those-who-run/chassis/compare/v4.5.5...v{cls.CHASSIS_VERSION})\n\n"
            "### Bug Fixes\n\n* a fix only chassis has\n",
            encoding="utf-8",
        )
        cls.dst = tmp / NAME
        try:
            copier_copy(cls.src, cls.dst, False)
        except AssertionError:
            cls._tmp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_new_repository_starts_at_0_0_0(self):
        self.assertEqual((self.dst / MANIFEST).read_text(encoding="utf-8"), FIRST_MANIFEST)

    def test_chassiss_changelog_stays_behind(self):
        self.assertFalse((self.dst / "CHANGELOG.md").exists())
        for path in sorted(files(self.dst)):
            with self.subTest(path=path):
                text = (self.dst / path).read_text(encoding="utf-8")
                self.assertNotIn(self.CHASSIS_VERSION, text)
                self.assertNotIn("a fix only chassis has", text)

    def test_a_repositorys_own_version_is_never_overwritten(self):
        # _skip_if_exists names the manifest by its path in the repository, without
        # the template suffix; --overwrite would replace any file it doesn't match.
        dst = Path(self._tmp.name) / "released"
        dst.mkdir()
        released = '{\n  ".": "0.3.0"\n}\n'
        (dst / MANIFEST).write_text(released, encoding="utf-8")
        copier_copy(self.src, dst, False, "--overwrite")
        self.assertEqual((dst / MANIFEST).read_text(encoding="utf-8"), released)
        self.assertTrue((dst / "go.mod").is_file())


if __name__ == "__main__":
    unittest.main()
