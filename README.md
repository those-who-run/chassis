# Chassis

The Go template, made with copier, that Those Who Run v2 repositories
start from: the layout, `make check`, CI, releases and the guardrails
built in.
It holds no component of its own; each Go component's repository is
made from it.

Issues are off in this repository. Every issue, the roadmap and the decisions
(ADRs) live in [those-who-run/paddock](https://github.com/those-who-run/paddock). A pull request here closes
its paddock issue with `Closes those-who-run/paddock#N.`

## Checks

`make check` runs what CI runs; [`AGENTS.md`](AGENTS.md) says what that is and
what a new clone runs first.
