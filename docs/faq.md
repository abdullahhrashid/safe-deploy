# FAQ

## Why not just use Kubernetes?

If Kubernetes is already in your life, by all means use it — its
Deployment + Service objects do blue-green (and far more) better than
this tool ever will. `safe-deploy` is for the case where Kubernetes is
not in your life and forcing it to be costs more than it saves: a
single VPS, two ops people, five services, no platform team.

## Why not docker-compose?

Compose is great at "bring this stack up". It is not great at
zero-downtime updates: `docker compose up -d` for a single service
recreates the container, which means a small but real outage. Tools like
`docker rollout` exist to bolt blue-green onto compose; `safe-deploy`
takes a similar approach but ships its own status TUI and treats the
deploy/rollback flow as a first-class operation rather than a recipe.

## Why not Traefik / Caddy / nginx with config reloads?

You absolutely can. `safe-deploy` opted for a network-alias swap
because it requires *no* additional process — no proxy to install, no
reload to coordinate. If you already have a reverse proxy and want
`safe-deploy` to drive *its* config instead of swapping aliases, that's
a reasonable contribution; today the tool doesn't do it.

## Can I run `safe-deploy` on multiple hosts?

Each host runs its own `safe-deploy` independently against its own
local Docker daemon. There is no cluster mode and no plan to add one.
For multi-host coordination you've outgrown the tool's scope.

If you do want N hosts behind the same DNS name, run `safe-deploy up`
on each one in your CI pipeline (sequentially, not in parallel —
you'll lose the zero-downtime guarantee otherwise unless you also
have a load balancer in front to drain connections).

## Does this support canary or progressive delivery?

No. The flip is binary: one moment all traffic is on blue, the next
moment all traffic is on green. If you need 5%-10%-50%-100% rollouts,
you need a real traffic-splitting proxy or service mesh — neither of
which `safe-deploy` is.

## What about database migrations?

Out of scope. Blue-green only solves "the new app version is live with
zero downtime". If the new app version requires schema that the old
version can't read, both will fail during the swap window. The
canonical answer is **expand-and-contract migrations**:

1. Deploy a backward-compatible schema change (e.g. add a nullable
   column).
2. Deploy app code that writes both old and new columns.
3. Backfill.
4. Deploy app code that reads from the new column only.
5. Deploy a contract migration that drops the old column.

`safe-deploy` is the tool that does steps 2 and 4 with zero downtime.
Steps 1, 3, 5 are yours to run before/after.

## What about secrets?

`safe-deploy` passes the `env` map straight through to Docker. For
production secrets, fill in the values from your CI's secret store at
deploy time (e.g. environment substitution in your CI YAML), or move to
Docker Swarm secrets / a dedicated secret manager. Don't commit
secrets to `safe-deploy.yaml`.

## What about WebSockets / long-lived connections?

The flip happens at the DNS-resolution layer (network alias). Existing
TCP connections to the old container keep going until the client
reconnects. If your app speaks WebSockets / SSE / gRPC streaming, plan
for clients to drop and reconnect within your tolerance window after a
deploy.

## Does it work on Windows / macOS?

Yes. The TUI runs in any modern terminal. The engine talks to whatever
Docker daemon `docker.from_env()` finds — Docker Desktop on
macOS/Windows works out of the box.

The example commands in the docs use POSIX shell syntax. Translate as
needed (`set` → `$env:` in PowerShell, etc.).

## Why Python and not Go?

Both would be fine. Python won because Textual is one of the best TUI
frameworks anywhere, and the docker-py SDK is very mature. The whole
codebase is ~700 lines; if you'd rather have a Go port, it's a short
weekend.

## Is it production-ready?

It's intentionally small and you should read it before trusting it. The
deploy path is straightforward and conservative — it never removes the
previously-active container, never proceeds past a failed health check,
and stores no critical state outside Docker. That said: **no test
suite ships with the project yet.** Pin a known-good commit and add
your own integration test against a throwaway VM before relying on it
for paying customers.

## Can I contribute?

Yes — see [architecture.md](./architecture.md) for the lay of the land.
Useful additions:

- A test suite (the `DockerDriver` boundary makes this very tractable).
- Pre/post deploy hooks per app.
- A `--watch` mode for `status` that streams updates.
- A reverse-proxy backend (Traefik/Caddy/nginx) as an alternative to
  network-alias swapping, for setups that already have a proxy.

Keep changes small and the codebase readable — that's the whole point
of this tool over heavier alternatives.
