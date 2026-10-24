# Chassis

The Go template for Those Who Run v2 repositories, a copier template: each
Go component's repository is made from it with `copier copy`, with the
layout, `make check`, CI, releases and the guardrails built in.
It holds no component of its own, and no `copier.yml` yet: that arrives
with those-who-run/paddock#21.

Issues are off in this repository. Every issue, the roadmap and the decisions
(ADRs) live in [those-who-run/paddock](https://github.com/those-who-run/paddock). A pull request here
names its paddock issue: `Closes those-who-run/paddock#N.` when it meets every
acceptance criterion, `Part of those-who-run/paddock#N` otherwise
([`AGENTS.md`](AGENTS.md)).

## Checks

`make check` runs what CI runs; [`AGENTS.md`](AGENTS.md) says what that is and
what a new clone runs first.
