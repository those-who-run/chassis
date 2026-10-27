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

- A Go module: `go.mod` with the Go version and a `toolchain` line, and with an
  image `cmd/<name>/main.go` and the example service in
  [`internal/service`](internal/service/service.go) with its tests; a library
  gets a placeholder package instead ("Without an image").
- `make check`, the same checks as CI ([`AGENTS.md`](AGENTS.md)), and
  [`.golangci.yml`](.golangci.yml). golangci-lint and govulncheck are pinned in
  [`tools/go.mod`](tools/go.mod) and run with `go tool -modfile=tools/go.mod`.
- Commit hooks for Go (gofmt, `go mod tidy` and golangci-lint) beside the
  language-neutral ones, and [`docs/dependencies.md`](docs/dependencies.md),
  which has a row for each direct dependency in `go.mod`, held to it by
  [`internal/dependencies`](internal/dependencies/dependencies_test.go).
- CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): `test`
  (`make test`), `checks / checks` and `go / check`, from the reusable workflows in
  `those-who-run/.github`, pinned by commit SHA. They run on every PR, on each push
  to `main` and in the merge queue (`merge_group`), so a repository can turn the
  queue on; [`tests/test_workflow_triggers.py`](tests/test_workflow_triggers.py)
  holds them to it.
- With an image: the [`Dockerfile`](Dockerfile) (multi-stage, base images pinned
  by digest, a static binary run as a non-root user) and
  [`image.yml`](.github/workflows/image.yml), which builds and smoke-tests the image
  on every PR and in the merge queue (`image / build`) and pushes nothing.
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
   repository ships an image. Over a foundation repository, the files it shares
   with chassis take chassis's Go versions, and copier asks before overwriting
   each: the README gets the template's sections, `AGENTS.md`, the `Makefile`,
   `ci.yml` and `.pre-commit-config.yaml` the Go checks and rules, and
   `.gitignore`, `scripts/docs_links.py` and its test skip `build/`, where
   `make` writes. Over `salsa`'s `main` as a library, those eight files change
   (`.github/workflows/ci.yml`, `.gitignore`, `.pre-commit-config.yaml`,
   `AGENTS.md`, `Makefile`, `README.md`, `scripts/docs_links.py` and
   `tests/test_docs_links.py`); the rest is new. Review each before committing.
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
`release-pr.yml` dispatches no release workflow: a release is its tag. The
release PR's header (`pull-request-header` in `release-please-config.json`) says
so: merging tags the commit and creates the GitHub release, with no release
workflow. It has no
example service either: no `cmd/` and no `internal/service/`. A library gets
the module, the tools and the checks, and a placeholder package in its root,
`doc.go` with one function, `Name`, and `doc_test.go` with its example, which
the library's own API and tests replace. A package is needed for the checks to
mean anything: with no Go code, `go build`, go vet, golangci-lint and
govulncheck have nothing to look at, and with no statements `go tool cover`
reports 0 % coverage, so `make check` and CI's `go / check` would fail the
coverage floor. `release-pr.yml` still grants `actions: write`: GitHub refuses
to start a reusable workflow whose jobs ask for more than the caller grants,
whether or not they run.

To drop the image later, run `copier update --data image=false`, which also
deletes the example service where the repository hasn't changed it and adds the
placeholder package; or by hand, delete those four files, `cmd/` and
`internal/service/`, set `release-workflow: ""` in `release-pr.yml`, take the
release workflow out of `pull-request-header` in `release-please-config.json` and
keep a package with tests in the module. Then take `image / build` out of the
repository's `checks` in `repos.json`.

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
- [`docs/dependencies.md`](docs/dependencies.md) is copied as it is, with
  chassis's empty table, and from then on holds the repository's own rows.
  `copier update` merges the template's later changes into it three ways, as it
  does for `go.mod`, so a row chassis adds arrives with the `require` it
  explains, and the repository's own rows stay.
- A library's placeholder package exists only as templates,
  `[% if not image %]doc.go[% endif %].jinja` and its test, whose names render
  empty, and so are skipped, for a repository with an image. The render without
  an image runs every check on them.
- copier's delimiters are `[[ ]]` and `[% %]`, not `{{ }}` and `{% %}`, so the
  GitHub Actions expressions in the workflows stay as they are.
- chassis's releases stay its own: its `CHANGELOG.md` is left out, and a new
  repository's `.release-please-manifest.json` starts at `0.0.0` and is never
  touched by `copier update` (`_skip_if_exists`), so the repository's versions
  follow its own releases, not chassis's.
- `release-please-config.json` sets `initial-version` to `0.1.0`. A manifest at
  `0.0.0` has no release tag behind it, so release-please treats the first
  release as an initial one, which `bump-minor-pre-major` doesn't reach. Without
  the setting it would be `1.0.0`, as chassis's own first release was.
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
