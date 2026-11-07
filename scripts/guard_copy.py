"""Check that this repository's copies of the agent files are the canonical ones.

The guard, the settings that run it and the skills and agents' briefs live once, in
those-who-run/.github's ``agent/``, and each repository copies them unchanged
(``agent/README.md`` there). This checks the copies here byte for byte against
``agent/`` at the commit this repository's CI pins for ``checks.yml``, so there is
one pinned ``.github`` version to bump: a bump of that pin fails this check until the
copies are brought up to the same commit, in the same PR.

What is copied where is ``agent/copies.json`` at that commit: a JSON object of source
path in ``.github`` to destination path here, every destination under ``.claude/``.
A commit from before the manifest (a 404 for it) copies the guard and the settings
alone.

- each file the manifest lists is in ``.github`` at that commit, and the file at its
  destination here is the same, byte for byte; without a manifest,
  ``.claude/hooks/guard.py`` is ``agent/guard.py`` and ``.claude/settings.json`` is
  ``agent/settings.json``;
- no file is left over from an earlier release: a file git tracks at
  ``.claude/skills/twr-*/**`` or ``.claude/agents/twr-*.md`` is a destination in the
  manifest. Without a manifest there are no such files. A repository's own skills
  and agents take another prefix;
- a manifest that can't be read as that object, sends a file outside ``.claude/``,
  names a path with ``..`` in it, or leaves out the guard or the settings fails the
  check: it is never skipped, and nothing is compared against it;
- ``.claude/guard.json``, this repository's own values, loads with the guard's own reader,
  since a config the guard can't read blocks every Bash command.

It fetches the files from raw.githubusercontent.com over HTTPS, so it needs the
network, and asks git which files are tracked (the files on disk, where the
directory is not in a git repository). ``make test`` and CI's ``test`` job run it.
Standard library only. Lifted from those-who-run/paddock's scripts/guard_copy.py
(paddock#20 R3).

    python3 scripts/guard_copy.py
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = Path(".github/workflows/ci.yml")
CANONICAL = "those-who-run/.github"
MANIFEST = "agent/copies.json"
# What a commit from before the manifest copies. A manifest lists both too, at these
# destinations, so that no manifest can take the guard out of the check.
COPIES = {
    "agent/guard.py": ".claude/hooks/guard.py",
    "agent/settings.json": ".claude/settings.json",
}
CONFIG = Path(".claude/guard.json")
# Where the shared skills and agents' briefs go. Git is asked about these alone.
SHARED_DIRS = (".claude/skills", ".claude/agents")

PIN = re.compile(
    r"^\s*uses:\s*" + re.escape(CANONICAL) + r"/\.github/workflows/checks\.yml@([0-9a-f]{40})\b",
    re.M,
)


def pinned_commit(ci_text: str) -> str:
    """The commit of those-who-run/.github that ci.yml calls checks.yml at."""
    pins = set(PIN.findall(ci_text))
    if len(pins) != 1:
        raise ValueError(
            f"{CI} should call {CANONICAL}'s checks.yml at one full commit SHA; found {sorted(pins) or 'none'}"
        )
    return pins.pop()


class FetchError(Exception):
    """A canonical file couldn't be fetched; the message says which and why."""


class NotFound(FetchError):
    """A 404: the file is not in those-who-run/.github at that commit, or the commit
    is not one of its commits."""


def fetch(commit: str, path: str) -> bytes:
    """A file of those-who-run/.github at a commit."""
    url = f"https://raw.githubusercontent.com/{CANONICAL}/{commit}/{urllib.parse.quote(path)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 (fixed https URL)
            return response.read()
    except (urllib.error.URLError, TimeoutError) as e:
        # A 404 is a pin that names no commit of .github, or a file that commit
        # doesn't have; anything else is most likely the network. One line either
        # way, as the other problems are.
        missing = isinstance(e, urllib.error.HTTPError) and e.code == 404
        if isinstance(e, urllib.error.HTTPError):
            e.close()  # it holds the response open
        reason = e.reason if isinstance(e, urllib.error.URLError) else e
        raise (NotFound if missing else FetchError)(
            f"could not fetch {url} ({reason}): check that the checks.yml pin in {CI} "
            "is a commit of those-who-run/.github, and the network"
        ) from None


class ManifestError(Exception):
    """The manifest can't be used. `reasons` says why, one for each thing wrong, each
    worded to follow the manifest's name."""

    def __init__(self, *reasons: str):
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


def plain(path: object) -> bool:
    """Whether path is a relative path of plain names, `/` between them: not
    absolute, and with no `..`, `.`, empty part, backslash or control character."""
    return (
        isinstance(path, str)
        and "\\" not in path
        and all(c.isprintable() for c in path)
        and all(part not in ("", ".", "..") for part in path.split("/"))
    )


def read_manifest(raw: bytes) -> dict[str, str]:
    """agent/copies.json as source path to destination path, or a ManifestError."""

    def no_repeats(pairs: list[tuple[str, object]]) -> dict[str, object]:
        # json keeps the last of two equal keys, which would hide the first copy.
        keys = [key for key, _ in pairs]
        if repeated := sorted({key for key in keys if keys.count(key) > 1}):
            raise ManifestError(*(f"lists {key!r} twice" for key in repeated))
        return dict(pairs)

    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=no_repeats)
    except (ValueError, RecursionError) as e:
        # Not UTF-8, not JSON, or JSON nested deeper than Python reads.
        raise ManifestError(f"is not JSON ({e})") from None
    if not isinstance(data, dict):
        raise ManifestError("is not a JSON object of source path to destination path")

    reasons = []
    sources: dict[str, str] = {}
    for source, copy in data.items():
        if not plain(source):
            reasons.append(f"names the source {source!r}, which is not a plain relative path (`..` is never one)")
        elif not plain(copy):
            reasons.append(f"sends {source} to {copy!r}, which is not a plain relative path (`..` is never one)")
        elif copy.split("/")[0] != ".claude" or "/" not in copy:
            reasons.append(f"sends {source} to {copy}, outside .claude/")
        elif copy in sources:
            reasons.append(f"sends both {sources[copy]} and {source} to {copy}")
        else:
            sources[copy] = source
    for source, copy in COPIES.items():
        if data.get(source) != copy:
            reasons.append(f"does not send {source} to {copy}, which every repository's guard needs")
    if reasons:
        raise ManifestError(*reasons)
    return data


def shared(path: str) -> bool:
    """Whether path is where a shared skill or agent's brief goes:
    `.claude/skills/twr-*/**` or `.claude/agents/twr-*.md`."""
    parts = path.split("/")
    if parts[:2] == [".claude", "skills"]:
        return len(parts) > 3 and parts[2].startswith("twr-")
    if parts[:2] == [".claude", "agents"]:
        return len(parts) == 3 and parts[2].startswith("twr-") and parts[2].endswith(".md")
    return False


def tracked(root: Path) -> list[str]:
    """The files git tracks under .claude/skills and .claude/agents. Where git can't
    say (no git, or a directory outside any repository, as one just made from the
    template is), every file there on disk, so that the check never passes for want
    of an answer."""
    try:
        done = subprocess.run(
            ["git", "ls-files", "-z", "--", *SHARED_DIRS], cwd=root, capture_output=True, check=False
        )
    except OSError:
        done = None
    if done is not None and done.returncode == 0:
        return sorted(name.decode("utf-8", "replace") for name in done.stdout.split(b"\0") if name)
    return sorted(
        path.relative_to(root).as_posix()
        for directory in SHARED_DIRS
        if (root / directory).is_dir()
        for path in (root / directory).rglob("*")
        if not path.is_dir()
    )


def config_problem(guard: Path, config: Path) -> str | None:
    """Why the guard can't read the config, or None when it can."""
    spec = importlib.util.spec_from_file_location("repo_guard", guard)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["repo_guard"] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    try:
        module.load_config(str(config))
    except module.ConfigError as e:
        return f"{config}: the guard can't read it: {e}"
    return None


def examine(root: Path = ROOT, get=fetch) -> tuple[list[str], dict[str, str] | None]:
    """What differs from the canonical files, one message each, and the manifest at
    the pinned commit: None where that commit has none, or where it wasn't read."""
    try:
        commit = pinned_commit((root / CI).read_text(encoding="utf-8"))
    except ValueError as e:
        return [str(e)], None
    at = f"at {commit[:12]}, the commit {CI} pins"
    manifest = None
    try:
        manifest = read_manifest(get(commit, MANIFEST))
    except NotFound:
        # A commit from before the manifest, or no commit of .github at all, which
        # the fetch of the guard below then reports.
        pass
    except FetchError as e:
        return [str(e)], None
    except ManifestError as e:
        return [
            f"{CANONICAL}'s {MANIFEST} {at}, {reason}: it is fixed in {CANONICAL}, and "
            "nothing here was compared against it"
            for reason in e.reasons
        ], None
    copies = COPIES if manifest is None else manifest

    problems = []
    for source, copy in sorted(copies.items()):
        try:
            want = get(commit, source)
        except NotFound as e:
            if manifest is None:
                return [str(e)], None
            problems.append(
                f"{CANONICAL}'s {MANIFEST} {at}, lists {source}, which is not in {CANONICAL} at "
                f"that commit: it is fixed in {CANONICAL}"
            )
            continue
        except FetchError as e:
            return [str(e)], None
        path = root / copy
        if not path.is_file():
            what = "is not a file" if path.exists() or path.is_symlink() else "is missing"
            problems.append(f"{copy} {what}: it is {CANONICAL}'s {source} {at}: copy it unchanged from there")
        elif path.read_bytes() != want:
            problems.append(
                f"{copy} is not {CANONICAL}'s {source} at {commit[:12]}, the commit {CI} pins: "
                "copy it unchanged from there"
            )
    wanted = set(copies.values())
    for path in tracked(root):
        if shared(path) and path not in wanted:
            if manifest is None:
                why = f"{CANONICAL} has no {MANIFEST} {at}, so it copies no skill or agent here"
                fix = "Delete it, or move the pin to the release it was copied from"
            else:
                why = f"{CANONICAL}'s {MANIFEST} {at}, does not list it"
                fix = "Delete it"
            problems.append(
                f"{path} is a stale copy: {why}. {fix}; a skill or agent of this repository's own "
                "takes a name that doesn't start with twr-"
            )
    if not problems and (reason := config_problem(root / COPIES["agent/guard.py"], root / CONFIG)):
        problems.append(reason)
    return problems, manifest


def check(root: Path = ROOT, get=fetch) -> list[str]:
    """What differs from the canonical files, one message each."""
    return examine(root, get)[0]


def main(root: Path = ROOT) -> int:
    problems, manifest = examine(root)
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 1
    if manifest is None:
        print(f"the guard and settings in .claude/ are {CANONICAL}'s agent/ at the commit {CI} pins")
    else:
        print(
            f"the {len(manifest)} files {CANONICAL}'s {MANIFEST} lists are the same in .claude/ "
            f"as in agent/ at the commit {CI} pins, and no other twr- skill or agent is tracked"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
