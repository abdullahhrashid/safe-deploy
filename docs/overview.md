# Overview

## What is safe-deploy?

`safe-deploy` is a single-host, single-operator tool for **blue-green Docker
deployments**. You declare your apps in a YAML file; the tool keeps two
container instances per app — one **blue**, one **green** — and lets you
flip traffic from one to the other only after the new instance has passed an
HTTP health check.

It ships with two front-ends over the same engine:

- a **Textual TUI** (`safe-deploy`) for interactive operations — status at a
  glance, one-key deploy and rollback, live logs;
- a **CLI** (`safe-deploy up`, `back`, `status`, `logs`) for scripts, cron
  jobs, and CI runners.

## Purpose

Most production teams know they want zero-downtime releases. The standard
answer is *"adopt Kubernetes (or Nomad, or ECS) and configure a blue-green or
canary controller"*. That answer is fine for teams with platform engineers.
For everyone else — the SME running 2–5 apps on a VPS, the small SaaS
shipping from a single host, the internal tool nobody wants to babysit — the
operational tax is too high.

`safe-deploy` exists for that gap. It assumes:

- you have one Docker host (or a small handful, used independently);
- you ship a handful of long-running HTTP services;
- you want releases to be **boring**: predictable, reversible, observable.

It deliberately does *not* try to grow into an orchestrator.

## Who is it for?

- **Solo developers and small ops teams** running production workloads on
  a single Docker host or VPS.
- **Internal tooling owners** who want releases on shared infra to be
  scriptable and rollback-able without paging anyone.
- **Educators and learners** wanting a small, readable codebase that
  demonstrates the blue-green pattern end-to-end.

## What you get

- **Zero-downtime swaps.** A release brings up the inactive colour, waits
  for it to pass an HTTP health check, then atomically reroutes traffic.
- **One-step rollback.** The previous colour is kept stopped (not removed)
  after a successful deploy, so reverting is just "start it and swap the
  alias back".
- **A real TUI.** Status table, action panel, scrolling activity log, and
  per-container log tailing — all from the terminal.
- **A scriptable CLI.** Same engine, exposed as commands suitable for CI
  pipelines or `cron`.
- **A tiny, readable codebase.** Roughly 700 lines of Python across config,
  state, deploy engine, CLI, and TUI.

## What you don't get (on purpose)

- Multi-host orchestration, scheduling, or autoscaling.
- A control-plane daemon, RBAC, or remote API.
- Canary, traffic-splitting, or progressive delivery.
- Anything that pretends to replace Kubernetes.

If you need those, you've outgrown `safe-deploy` — and that's a good problem.

## Design philosophy

1. **Boring beats clever.** The deploy path is a sequence of plain Docker
   API calls a human can read in one sitting.
2. **One host, one operator.** No daemons, no auth, no cluster state. State
   is a JSON file in `~/.safe-deploy/`.
3. **Default to safety.** Failing health checks abort the swap and tear down
   the candidate. Old colours stick around, stopped, until the next deploy.
4. **Two front doors, one engine.** The TUI and CLI both call the same
   `deploy.py` functions — what you can do interactively, you can script.
