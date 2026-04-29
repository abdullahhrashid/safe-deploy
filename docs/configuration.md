# Configuration reference

`safe-deploy` reads a single YAML file. Resolution order:

1. The path passed via `-c / --config`, if any.
2. `./safe-deploy.yaml` in the current working directory.
3. `~/.safe-deploy/config.yaml`.

The first one that exists wins. Generate a starter with `safe-deploy init >
safe-deploy.yaml`.

## File shape

```yaml
network: safe-deploy        # optional; default "safe-deploy"

apps:
  - name: web
    image: nginx
    tag: stable
    container_port: 80
    host_port: 8080
    network: safe-deploy    # optional; defaults to top-level network
    env:
      ENVIRONMENT: production
    healthcheck:
      path: /
      port: 80              # optional; defaults to container_port
      interval_s: 1.0
      timeout_s: 30
      expect_status: 200
```

## Top-level fields

### `network`
*(string, default `"safe-deploy"`)*

The name of the Docker bridge network all managed containers join. It is
created automatically on the first deploy if it doesn't exist. Pick
something else if `safe-deploy` would clash with a network you already
manage.

### `apps`
*(list, required)*

One entry per managed application. Each must have a unique `name`.

## Per-app fields

### `name` *(string, required)*

The app identifier. Used as the bare network alias and as the container
name prefix. Must be unique within the file. Stick to DNS-safe characters
(`a-z`, `0-9`, `-`) — Docker enforces this for network aliases.

### `image` *(string, required)*

The image repository, **without** the tag. Examples: `nginx`,
`ghcr.io/acme/api`, `registry.internal:5000/web`.

### `tag` *(string, default `"latest"`)*

The image tag deployed by default. The CLI's `--tag` flag and the TUI's
tag input override this at deploy time without modifying the file.

### `container_port` *(integer, default `80`)*

The port the container listens on internally. Used both as the
health-check target (unless `healthcheck.port` overrides) and as the
container side of the published-port mapping.

### `host_port` *(integer, optional)*

The host-side port to publish for *external* traffic. Only the **active**
colour publishes it — the inactive colour stays internal so the host port
isn't held twice.

Omit this field for apps that only receive traffic from other containers
on the same Docker network (those should connect via `http://<app>` and
let alias resolution handle the routing).

### `env` *(map of string→string, optional)*

Environment variables passed to both colours. Values are coerced to
strings.

```yaml
env:
  DATABASE_URL: postgres://db/app
  LOG_LEVEL: info
```

For secrets, prefer environment-substituted values (read from your CI
secret store) over committing them to the YAML.

### `network` *(string, optional)*

Override the network for this app. Most setups won't need this; it's
useful when you want one app to be reachable on a different bridge from
the rest.

### `healthcheck` *(object, optional)*

How `safe-deploy` decides the candidate is ready before swapping.

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `path` | string | `"/"` | URL path to GET. Use `/healthz` or similar if your app exposes one. |
| `port` | integer | `container_port` | Port to hit inside the container. |
| `interval_s` | float | `1.0` | Seconds between retries. |
| `timeout_s` | float | `30.0` | Total budget. If the candidate isn't healthy within this, the deploy aborts. |
| `expect_status` | integer | `200` | The HTTP status the candidate must return. |

The check connects to the container's IP on the bridge network — it does
not go through `host_port`. This means health checks work even when the
app isn't published externally.

If the container has no IP yet (rare, e.g. networking still settling), the
tool waits ~2 seconds and proceeds. This is a deliberate compromise to
avoid blocking forever on a container that's actually fine.

## Examples

### Minimal — internal-only API behind another reverse proxy

```yaml
apps:
  - name: api
    image: ghcr.io/acme/api
    tag: v1.2.0
    container_port: 8080
    healthcheck:
      path: /healthz
      timeout_s: 60
```

No `host_port`. Other containers reach it via `http://api:8080` on the
`safe-deploy` network. An external nginx/caddy already sitting on that
network would point upstream to `api`.

### Public web app

```yaml
apps:
  - name: web
    image: ghcr.io/acme/web
    tag: stable
    container_port: 3000
    host_port: 80
    env:
      NODE_ENV: production
    healthcheck:
      path: /healthz
      timeout_s: 45
      expect_status: 200
```

### Multi-app

```yaml
network: safe-deploy

apps:
  - name: web
    image: ghcr.io/acme/web
    tag: stable
    container_port: 3000
    host_port: 80

  - name: api
    image: ghcr.io/acme/api
    tag: stable
    container_port: 8080
    host_port: 8080
    healthcheck:
      path: /healthz

  - name: worker
    image: ghcr.io/acme/worker
    tag: stable
    container_port: 9000
    healthcheck:
      path: /metrics
```

`web` and `api` are publicly exposed; `worker` is internal-only and
health-checked via its metrics endpoint.

## What is *not* configurable

- **Resource limits / volumes / networks-of-networks.** Out of scope.
  If you need them, deploy a less opinionated wrapper and call out to
  `safe-deploy` for the swap step only.
- **Pre/post hooks.** Use your CI script around `safe-deploy up` for
  before/after work.
- **Multiple replicas per colour.** One container per colour by design.

## Validation

Configuration errors surface at load time:

```text
$ safe-deploy status
Error: config not found: /path/to/safe-deploy.yaml
```

Bad YAML (unparsable) raises a `yaml.YAMLError` with the line number.
Missing required fields (`name`, `image`) raise a clear `KeyError` from
the loader. There is no schema validator beyond that — keep configs
small and they don't need one.
