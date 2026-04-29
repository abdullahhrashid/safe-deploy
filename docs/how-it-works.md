# How it works

This is the conceptual model. If you'd rather read the code, see
[architecture.md](./architecture.md).

## The blue-green pattern, in one paragraph

For every app, there are two container instances: **blue** and **green**.
At any moment, exactly one of them — the *active colour* — is the one
serving traffic. To release a new version, you bring up the *inactive*
colour with the new image, wait for it to look healthy, then atomically
flip "which colour is active". The old colour becomes the inactive one,
ready to be replaced on the next release (or to be reactivated as a
rollback).

That's it. The reason it gives zero-downtime is that the new instance is
fully ready *before* any client touches it, and the flip happens in one
step.

## How `safe-deploy` flips traffic

The tricky part of blue-green is the flip. `safe-deploy` uses **Docker
network aliases** rather than a reverse proxy, because aliases require no
extra moving parts.

For an app named `web`, both containers join a shared bridge network
(default `safe-deploy`). The active container holds two aliases on that
network:

- `web-blue` (or `web-green`) — its colour-specific alias, always present;
- `web` — the **bare** alias, present only on the active colour.

Other services on the same network reach the app via `http://web`. The
Docker DNS resolver returns the IP of whichever container currently owns the
`web` alias. To swap, `safe-deploy`:

1. Disconnects both colour containers from the network;
2. Reconnects them, attaching the bare `web` alias to the new colour only.

From a caller's perspective, the resolution simply starts pointing at a
different IP. There is no proxy reload, no config rewrite, no restart.

For external traffic, `safe-deploy` publishes the configured `host_port`
only on the active colour. The inactive colour stays internal so its port
doesn't collide with the live one.

## End-to-end deploy timeline

Suppose `web` is currently serving from blue, and you run `safe-deploy up
web --tag 1.4.2`.

```
t0  read state          → active = blue
t1  pull image          → docker pull web-image:1.4.2
t2  remove stale green  → if a previous green container exists, force-remove
t3  start green         → run container, attach to network with alias web-green
t4  health check        → poll http://<green-ip>:<port><health-path>
                          until 200 OK or timeout
                          ── if it fails: remove green, abort, leave blue serving ──
t5  swap alias          → disconnect both; reconnect with web alias on green
t6  persist state       → state.json: active = green
t7  stop blue           → docker stop blue (kept, not removed)
t8  done                → log "web now serving from green"
```

If anything between `t1` and `t4` fails, blue is untouched and still
serving. If `t5` succeeds but you immediately notice the new version is
broken, `safe-deploy back web` reverses the swap by reactivating blue and
re-pinning the alias.

## Health checks

`safe-deploy` performs an **HTTP-level** health check after starting the
candidate. By default it does `GET /` against the container's IP on the
network and expects a 200 status. You can configure:

- `path` — the URL path to hit (e.g. `/healthz`);
- `port` — defaults to `container_port`;
- `interval_s` — how often to retry while waiting;
- `timeout_s` — total budget before the deploy aborts;
- `expect_status` — the HTTP status the candidate must return.

This is intentionally simpler than Docker's native HEALTHCHECK directive: it
checks the *external* contract (does the app respond on the network?) rather
than relying on the image author to ship a correct healthcheck.

## State

State is a single JSON file at `~/.safe-deploy/state.json`. For each app
it records the active colour and the last image deployed to each colour.
That's enough for the TUI to show status and for `back` to know which
colour to revive.

State is not the source of truth — Docker is. If you blow `state.json`
away, the next `status` call will rebuild a usable picture from container
labels (`safe-deploy.app`, `safe-deploy.color`, `safe-deploy.image`) that
each container is started with.

## Failure modes the tool handles

| Failure | What `safe-deploy` does |
|---|---|
| Image fails to pull | Falls back to a local image of the same tag if present; otherwise aborts before touching anything. |
| Candidate container exits during boot | Detected by the health-check loop (status != running) → aborts and removes the candidate. |
| Health check times out | Aborts, removes the candidate, leaves the active colour serving. |
| Network disconnect/reconnect partially fails | Active colour still has an old alias — operator can re-run `up`; the next deploy will re-attach aliases cleanly. |
| Rollback target was removed | `back` errors out clearly instead of pretending. |

## What it does *not* protect against

- **Database migrations.** If your new version requires schema changes,
  blue-green alone is not enough — you need expand/contract migrations or
  a maintenance window. `safe-deploy` cannot fix that.
- **Long-lived connections.** WebSockets and SSE streams keep talking to
  the old container until they reconnect. The flip is per-DNS-lookup, not
  per-byte.
- **External port exhaustion.** If two apps want the same `host_port`,
  Docker will refuse — by design.
