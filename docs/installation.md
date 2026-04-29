# Installation

## Prerequisites

- **Python 3.10+** — `safe-deploy` uses modern type-hint syntax (`A | B`).
- **Docker** — a running daemon reachable via the standard SDK channels:
  - Linux: `/var/run/docker.sock` (default);
  - macOS / Windows: Docker Desktop's pipe or socket;
  - Remote: set `DOCKER_HOST=tcp://...` and the appropriate TLS env vars.
- A **terminal that supports 256-colour output** for the TUI to render
  nicely (any modern terminal does — Windows Terminal, iTerm2, Alacritty,
  Kitty, GNOME Terminal, etc.).

The user running `safe-deploy` must be able to talk to the Docker daemon —
on Linux this typically means membership in the `docker` group (or
running with sudo, which is not recommended).

## Install from source

The project is currently a single repo; install it in editable mode:

```bash
git clone <your-clone-url> safe-deploy
cd safe-deploy
python -m pip install -e .
```

This installs the `safe-deploy` console script onto your `PATH` and pulls
in the dependencies (`textual`, `docker`, `pyyaml`, `click`).

> **Tip — use a virtualenv.** Don't install into the system Python on a
> production host:
> ```bash
> python -m venv .venv
> . .venv/bin/activate    # Windows: .venv\Scripts\activate
> python -m pip install -e .
> ```

## Verify

```bash
safe-deploy --version
safe-deploy --help
```

You should see the version string and the list of subcommands. If the
shell can't find `safe-deploy`, your virtualenv isn't active or your
`PATH` doesn't include the install location.

## Verify the Docker connection

```bash
python -c "import docker; print(docker.from_env().version()['Version'])"
```

This should print your Docker daemon version. If it errors, fix that
first — `safe-deploy` will fail with the same error otherwise.

## Where things live

| Path | Purpose |
|------|---------|
| `./safe-deploy.yaml` | Per-project config (preferred — picked up automatically when you run from the project dir). |
| `~/.safe-deploy/config.yaml` | Fallback global config if no per-project config is found. |
| `~/.safe-deploy/state.json` | Active-colour state per app. Created automatically. |
| Docker network `safe-deploy` | Created on first deploy. All managed containers join it. |
| Containers `safe-deploy_<app>_blue` / `_green` | The managed containers. Anything else is left alone. |

## Uninstall

```bash
pip uninstall safe-deploy
```

Optionally clean up Docker artefacts:

```bash
# stop and remove all managed containers
docker ps -a --filter "label=safe-deploy.app" -q | xargs -r docker rm -f

# remove the network (only if nothing else uses it)
docker network rm safe-deploy

# wipe state
rm -rf ~/.safe-deploy
```
