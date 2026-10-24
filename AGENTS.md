# Agents and contributors

`chassis` is part of Those Who Run v2; [`README.md`](README.md) says what it is.

The rules for every v2 repository live once, in paddock's
[`AGENTS.md`](https://github.com/those-who-run/paddock/blob/main/AGENTS.md), and apply here in full, for
coding agents and for people. This file adds only what is specific to this
repository, and never repeats or weakens a rule from there.

## Issues

Issues are off here: every issue lives in
[those-who-run/paddock](https://github.com/those-who-run/paddock/issues). Read one with
`gh issue view N -R those-who-run/paddock --comments`. A PR here says
`Closes those-who-run/paddock#N.` only when every acceptance criterion is met,
and `Part of those-who-run/paddock#N` otherwise, as paddock's `AGENTS.md` says.

## Definition of done

`make check` passes. It runs what CI runs, in three parts:

- the commit hooks on every file (CI's `checks / checks`);
- the Go checks, in the order go.yml in `those-who-run/.github` runs them (CI's
  `go / check`): gofmt, `go mod tidy` for the module and `tools/go.mod`, go vet,
  golangci-lint with [`.golangci.yml`](.golangci.yml), the tests with the race
  detector (a skipped test fails, and so does total coverage below 90 %), go
  build and govulncheck;
- the repository's own checks (with the Go tests, CI's `test`): every internal
  Markdown link and anchor resolves, the guard and settings in `.claude/` are
  `those-who-run/.github`'s `agent/` at the commit CI pins, and the tests in
  `tests/`.

It needs Go (the version in `go.mod`'s `toolchain` line, which the `go`
command fetches when `GOTOOLCHAIN` allows it), `python3`, `pre-commit` and the
network. CI's `image / build`, where the repository ships an image, also builds
the Dockerfile and smoke-tests the image; `make check` doesn't.

A change also carries a test for each acceptance criterion of its issue,
docs changed in the same PR as what they describe, and a recording that
pins a behaviour where one applies.

This file's rules for Go (tool versions, formatting, generated files, where
dependencies are declared and locked) arrive with those-who-run/paddock#22.

## Make targets

- `make check`: everything a PR must pass, as CI runs it.
- `make test`: the Go tests with the coverage floor, and the repository's own
  checks: CI's `test` job, while iterating.
- `make fmt`: formats the Go code; `make lint`: golangci-lint.
- `make hooks`: installs the commit hooks. A new clone or worktree runs it
  once, so the hooks run on every commit and commit message.

`make help` lists the rest, among them each Go check on its own.

## The guard

`.claude/settings.json` and `.claude/hooks/guard.py` are copies: a change to
them is made in `those-who-run/.github`, then copied here unchanged with the
bump of the `checks.yml` pin in `.github/workflows/ci.yml`.
`.claude/guard.json` holds this repository's own values.
