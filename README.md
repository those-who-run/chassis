# Chassis

The Go template for Those Who Run v2 repositories, a
[copier](https://github.com/copier-org/copier) template: each Go component's
repository is made from it with `copier copy`, with the layout, `make check`,
CI, releases and the guardrails built in, and takes the template's later changes
with `copier update`.

Issues are off in this repository. Every issue, the roadmap and the decisions
(ADRs) live in [those-who-run/paddock](https://github.com/those-who-run/paddock). A pull request here
names its paddock issue: `Closes those-who-run/paddock#N.` when it meets every
acceptance criterion, `Part of those-who-run/paddock#N` otherwise
([`AGENTS.md`](AGENTS.md)).

## What a repository gets

- A Go module: `cmd/<name>/main.go`, the example service in
  [`internal/service`](internal/service/service.go) with its tests, and `go.mod`
  with the Go version and a `toolchain` line.
- `make check`, the same checks as CI ([`AGENTS.md`](AGENTS.md)), and
  [`.golangci.yml`](.golangci.yml). golangci-lint and govulncheck are pinned in
  [`tools/go.mod`](tools/go.mod) and run with `go tool -modfile=tools/go.mod`.
- CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): `test`
  (`make test`), `checks / checks` and `go / check`, from the reusable workflows in
  `those-who-run/.github`, pinned by commit SHA.
- With an image: the [`Dockerfile`](Dockerfile) (multi-stage, base images pinned
  by digest, a static binary run as a non-root user) and
  [`image.yml`](.github/workflows/image.yml), which builds and smoke-tests the image
  on every PR (`image / build`) and pushes nothing.
- Releases with release-please
  ([`release-pr.yml`](.github/workflows/release-pr.yml),
  [`release-please-config.json`](release-please-config.json), release type `go`,
  starting at `0.0.0`), and for an image
  [`release.yml`](.github/workflows/release.yml), which publishes
  `ghcr.io/those-who-run/twr-<name>:X.Y.Z` from the release tag.
- OpenSSF Scorecard, weekly ([`scorecard.yml`](.github/workflows/scorecard.yml)).
  It gates nothing.
- The foundation every v2 repository has: [`AGENTS.md`](AGENTS.md),
  [`CLAUDE.md`](CLAUDE.md), `.github/CODEOWNERS`, the guard in `.claude/`, the
  commit hooks, `renovate.json` and the licence.

## Conventions

Kept minimal, since every Go component copies them:

- **Configuration from the environment**, read once at start-up into a typed
  struct ([`ConfigFromEnv`](internal/service/service.go)); an unset variable
  takes its default and a value that can't be read stops the process. The
  example reads `ADDR` (`:8080`) and `LOG_LEVEL` (`info`).
- **Logging with `log/slog`, as JSON** on standard output, one object per line,
  with key-value pairs (golangci-lint's `sloglint` holds them to that).
- **A health endpoint**, `GET /healthz`, which answers 200 while the process can
  serve. The image's smoke test calls it.

## Making a repository from this template

The maintainer's steps; agents never create repositories or change settings.

1. `chassis` has a release: `copier copy` is pinned to a tag.
2. The repository exists on GitHub, with its foundation PR merged.
3. Install copier at the version this repository pins, from a clone of
   `chassis`:

   ```sh
   python3 -m venv build/copier-venv
   build/copier-venv/bin/pip install --require-hashes -r .github/requirements-copier.txt
   ```

4. In a clone of the new repository, on a branch:

   ```sh
   <chassis>/build/copier-venv/bin/copier copy --vcs-ref vX.Y.Z \
     https://github.com/those-who-run/chassis.git .
   ```

   It asks for the name, the README's title and first paragraph, and whether the
   repository ships an image. Over a foundation repository, only `README.md` and
   `AGENTS.md` differ besides the new files; copier asks before overwriting each.
   `.copier-answers.yml` records the tag and the answers: commit it.
5. `make check`, then a PR. Its CI runs `test`, `checks / checks`, `go / check`
   and, with an image, `image / build`.
6. Settings, once that PR is merged:
   - in `those-who-run/.github`'s `scripts/repos.json`, add `go / check` (and
     `image / build` for an image) to the repository's `checks`, and for an image
     set `publishes`, then run `scripts/protect-repo.sh`;
   - install the release App on the repository and create its
     `release-please` environment, as `those-who-run/.github`'s
     [workflows README](https://github.com/those-who-run/.github/blob/main/.github/workflows/README.md#the-repositorys-settings)
     says;
   - for an image, the `release` environment (`v*` tags only, the maintainer as
     required reviewer), and the package made public after its first push.

### Taking the template's changes

Renovate's copier manager reads `.copier-answers.yml` and proposes each new
`chassis` release as a PR that runs `copier update`. By hand, on a branch:
`copier update --vcs-ref vX.Y.Z`. copier merges the template's changes with the
repository's own three ways, leaving conflicts marked for review.

### Without an image

A library (`salsa`, `contracts`) answers no to "Does it ship a container
image?". The repository then has no `Dockerfile`, `.dockerignore`,
`.github/workflows/image.yml` or `.github/workflows/release.yml`, and
`release-pr.yml` dispatches no release workflow: a release is its tag. To drop
the image later, run `copier update --data image=false`, or delete those four
files and set `release-workflow: ""` in `release-pr.yml`; then take
`image / build` out of the repository's `checks` in `repos.json`.

## How the template is laid out

The repository is its own rendered project, for the name `chassis`: `make check`
and CI check it as they would any component. [`copier.yml`](copier.yml) holds the
questions and what stays out of a new repository.

- A file a repository gets as it is (the workflows, the Makefile, the foundation)
  is copied unchanged.
- A file that needs the repository's own values has a sibling with the `.jinja`
  suffix, which copier renders in its place. Most include chassis's own file and
  put the repository's name for `chassis`, so a change to the file, a Renovate
  bump among them, reaches the template with nothing to copy by hand.
  `README.md.jinja` is a README of its own; `cmd/[[name]]/` renders as
  `cmd/<name>/`.
- copier's delimiters are `[[ ]]` and `[% %]`, not `{{ }}` and `{% %}`, so the
  GitHub Actions expressions in the workflows stay as they are.
- `release.yml` here never publishes: its jobs run only outside
  `those-who-run/chassis`, and a rendered repository's copy has no such
  condition.

## Checks

`make check` runs what CI runs; [`AGENTS.md`](AGENTS.md) says what that is and
what a new clone runs first. Here `make test` also renders the template, with
and without an image, into a temporary directory, checks every file against
chassis's own, and runs the rendered repository's checks there
([`tests/test_template.py`](tests/test_template.py)), so a broken template fails
CI's `test`. It installs copier from
[`.github/requirements-copier.txt`](.github/requirements-copier.txt), hash-checked,
into `build/copier-venv`.
