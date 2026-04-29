# Architecture

For contributors and the curious. The whole codebase is small enough to
read in an afternoon — this doc just gives you the map.

## Module layout

```
safe_deploy/
├── __init__.py     version string
├── __main__.py     allows `python -m safe_deploy`
├── cli.py          click-based CLI; also launches the TUI
├── config.py       YAML loader, dataclasses for AppSpec / HealthCheck
├── state.py        active-colour persistence in ~/.safe-deploy/state.json
├── deploy.py       the engine: deploy(), rollback(), DockerDriver, health checks
└── tui.py          Textual app: SafeDeployApp + widgets + workers
```

Roughly 700 lines total. There are no other internal modules.

## Layering

```
┌──────────────────────────┐   ┌────────────────────┐
│ tui.py (Textual app)     │   │ cli.py (click)     │
└────────────┬─────────────┘   └─────────┬──────────┘
             │                           │
             ▼                           ▼
        ┌────────────────────────────────────┐
        │ deploy.py — engine                  │
        │   deploy(), rollback(),             │
        │   DockerDriver, wait_healthy(), …   │
        └─────────┬───────────────┬────────────┘
                  │               │
          ┌───────▼─────┐  ┌──────▼──────┐
          │ config.py   │  │ state.py    │
          │ (read-only) │  │ (read/write)│
          └─────────────┘  └─────────────┘
                  │
                  ▼
            Docker daemon
```

Both front-ends call the same engine functions with the same arguments.
There is no front-end-specific logic in `deploy.py`; the TUI passes a
`log` callback that writes to its activity panel, the CLI passes
`click.echo`, and tests can pass a list-appender.

## The deploy engine (`deploy.py`)

Two public entry points:

```python
def deploy(spec, state, driver=None, log=...) -> DeployResult: ...
def rollback(spec, state, driver=None, log=...) -> DeployResult: ...
```

Both follow the same skeleton:

1. Decide the target colour.
2. Bring up / unstop a candidate container (`DockerDriver.start_color`).
3. `wait_healthy(...)` polls HTTP until ready or the budget runs out.
4. On failure: tear the candidate down, raise `DeployError`.
5. On success: `DockerDriver.swap_alias(...)`, persist new active colour.
6. Stop the previous colour (kept, not removed).

Failure paths never touch the previously-active container — that's the
core safety property of the design.

### `DockerDriver`

A thin wrapper around `docker.from_env()` exposing exactly the operations
the engine needs:

| Method | Purpose |
|--------|---------|
| `ensure_network` | Idempotent network creation |
| `pull` | Pull image; fall back to local copy if registry is unreachable |
| `start_color` | Run a container with the safe-deploy labels and aliases |
| `swap_alias` | Disconnect both colours, reconnect with the bare alias on the new one |
| `stop_color` / `remove_color` | Lifecycle mgmt |
| `container_status` | Used by the TUI table |
| `tail_logs` | Used by the TUI logs tab and `safe-deploy logs` |

Keeping every Docker call behind this wrapper makes the engine testable
with a fake driver.

### Health check (`wait_healthy`)

Resolves the candidate's IP on the configured network, then polls
`http://<ip>:<port><path>` with a tight loop until the deadline. It
also re-checks the container's `status` each iteration and bails early
if the container has exited (a fast-fail path so we don't waste 30s on
a container that crashed at second 1).

Polling uses the Python stdlib (`urllib.request`) on purpose — no
`requests` dependency for one feature.

## State (`state.py`)

A `State` object wraps `~/.safe-deploy/state.json`. The schema:

```json
{
  "apps": {
    "<name>": {
      "active": "blue",
      "colors": {
        "blue":  {"image": "nginx:stable"},
        "green": {"image": "nginx:1.27"}
      }
    }
  }
}
```

The file is read on construction, written after every mutation. A
`threading.Lock` guards in-process concurrent writes (the TUI workers
run on background threads).

State is **not authoritative.** Docker is. The state file is a cache of
"which colour did we last decide was active". If you delete it,
`safe-deploy status` still works because container status comes from
Docker; you just lose the active-colour memory until the next deploy.

## Config (`config.py`)

Plain dataclasses (`AppSpec`, `HealthCheck`, `Config`) populated by
`Config.load(path)`. No validation library, no schema engine — the file
is small enough that constructor errors and `KeyError`s give adequate
feedback.

## CLI (`cli.py`)

Click-based, one function per subcommand. Each one calls `_load(...)`
to get `(config, state, driver, path)`, then dispatches into the engine.
The `main` group is `invoke_without_command=True` and falls through to
the TUI when no subcommand is given.

## TUI (`tui.py`)

A single `SafeDeployApp` Textual app. Notable bits:

- **Layout** is composed in `compose()` from standard Textual widgets
  (`Header`, `Footer`, `DataTable`, `RichLog`, `TabbedContent`, …).
- **Reactivity:** `selected_app` is a `reactive[str | None]` updated
  from `DataTable.RowHighlighted` — every action reads from it.
- **Concurrency:** deploy/rollback run via `@work(thread=True,
  exclusive=True, group="ops")` so the UI thread stays responsive and
  one operation cancels the previous of the same kind.
- **Cross-thread logging:** the engine receives a `log` callback that
  posts into the activity log via `App.call_from_thread(...)`, the
  Textual-blessed way to update widgets from a worker.

There's no custom CSS theme — colour comes from Textual's default and
inline `[bold cyan]` markup in the table cells.

## Testability

The engine is straightforward to test with a fake driver:

```python
class FakeDriver:
    def ensure_network(self, name): pass
    def pull(self, ref, log=lambda _: None): pass
    def start_color(self, spec, color, log=...): return _Stub()
    # …etc
```

There's no test suite shipped yet — adding one would be a great first
contribution. Reasonable starting points: `wait_healthy` against an
embedded HTTP server, and `deploy()`/`rollback()` against a `FakeDriver`
that records the call sequence.

## Dependency surface

| Package | Why |
|---------|-----|
| `textual` | TUI framework |
| `docker` | Docker SDK for Python |
| `pyyaml` | Config parsing |
| `click` | CLI parsing |

All four are widely used and stable. The runtime dependency footprint is
intentionally small.

## Adding a feature

A worked example: "support a `pre_deploy` shell hook per app".

1. Add `pre_deploy: str | None = None` to `AppSpec` and read it in
   `Config.load`.
2. In `deploy.py`, between `pull` and `start_color`, run
   `subprocess.run(spec.pre_deploy, shell=True, check=True)` and call
   `log(...)` on each line.
3. Document it in `docs/configuration.md`.

That's the rhythm: data shape in `config.py`, behaviour in `deploy.py`,
exposure in `cli.py` / `tui.py` only if it changes the user surface.
