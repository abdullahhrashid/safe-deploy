# Getting started

A worked example: deploy `nginx`, switch versions, roll back. Total time
~5 minutes if Docker is already running.

## Quick start

```bash
# 1. install
pip install -e .

# 2. drop a config in the current directory
safe-deploy init > safe-deploy.yaml

# 3. launch the TUI
safe-deploy
```

In the TUI: select `web`, press `d` to deploy, watch the activity log,
then press `b` to roll back. That's the whole loop.

The rest of this page walks the same flow with more detail.

## Step 1 — Generate a starter config

```bash
safe-deploy init > safe-deploy.yaml
```

Open `safe-deploy.yaml`. The default declares one app called `web` running
`nginx:stable` on host port `8080`. For our walkthrough, leave it as-is.

See [configuration.md](./configuration.md) for the full reference.

## Step 2 — First deploy (CLI)

We'll use the CLI so each step is visible:

```bash
safe-deploy status
```

Output: `web  image=nginx:stable  active=none` — nothing deployed yet.

```bash
safe-deploy up web
```

You should see (abbreviated):

```
=== deploy web :: none → blue ===
pulling nginx:stable…
starting blue from nginx:stable
health-checking http://172.x.x.x:80/ (≤30s)
healthy ✓
alias 'web' → blue
=== web now serving from blue ===
deployed web → blue
```

Verify:

```bash
curl http://localhost:8080
docker ps --filter "label=safe-deploy.app=web"
```

You'll see one running container, `safe-deploy_web_blue`, on the
`safe-deploy` bridge network with the bare alias `web` attached.

## Step 3 — Deploy a different version

Let's pretend you've just shipped a new release. We'll switch the tag:

```bash
safe-deploy up web --tag 1.27
```

Watch the timeline:

```
=== deploy web :: blue → green ===
pulling nginx:1.27…
starting green from nginx:1.27
healthy ✓
alias 'web' → green
stopping blue
old blue kept stopped for fast rollback
=== web now serving from green ===
```

`docker ps -a --filter "label=safe-deploy.app=web"` now shows blue
**stopped** and green **running**. Traffic on `localhost:8080` is now
served by green.

## Step 4 — Roll back

```bash
safe-deploy back web
```

`safe-deploy` starts the blue container back up, re-runs the health check
against it, swaps the alias, and stops green. `localhost:8080` is back on
the original version. No image was pulled, no fresh container was created
— it's literally the previous instance brought back online.

## Step 5 — Use the TUI

Now run:

```bash
safe-deploy
```

You'll see:

- a top status bar (config path, network, app count);
- a left-pane table of apps with image, active colour, and per-colour status;
- a right-pane action panel with a tag input, **Deploy**, **Rollback**,
  and **Refresh** buttons, plus a scrolling activity log;
- a "Container logs" tab for tailing blue/green logs in place.

Keys:

| Key | Action |
|-----|--------|
| `d` | Deploy the selected app (uses the tag entered in the input, or the configured default) |
| `b` | Rollback the selected app |
| `r` | Refresh the table |
| `l` | Show blue logs in the Container logs tab |
| `q` | Quit |

The table refreshes automatically every 5 seconds.

See [tui-guide.md](./tui-guide.md) for a full walkthrough.

## Step 6 — Cleanup

To remove the demo:

```bash
docker rm -f safe-deploy_web_blue safe-deploy_web_green 2>/dev/null
docker network rm safe-deploy 2>/dev/null
rm -rf ~/.safe-deploy
```

## Where to go next

- Add your real apps to `safe-deploy.yaml` — see
  [configuration.md](./configuration.md).
- Wire `safe-deploy up <app> --tag $CI_COMMIT_TAG` into your CI — see
  [cli-reference.md](./cli-reference.md).
- Read [how-it-works.md](./how-it-works.md) to understand exactly what
  happens during a swap.
