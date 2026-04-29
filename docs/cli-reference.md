# CLI reference

The `safe-deploy` command exposes the same engine the TUI does. Use the
TUI for interactive work; use these commands for scripts, CI, and cron.

## Global options

```text
safe-deploy [OPTIONS] COMMAND [ARGS]...

  Blue-green Docker deployments with a TUI.

Options:
  -c, --config PATH  path to safe-deploy.yaml
  --version          Show the version and exit.
  -h, --help         Show this message and exit.
```

`-c / --config` accepts any readable path. If omitted, resolution falls
back to `./safe-deploy.yaml` then `~/.safe-deploy/config.yaml`.

Running `safe-deploy` with no subcommand launches the TUI.

## `safe-deploy init`

Print a sample configuration to stdout. Pipe it into a file to start a
new project:

```bash
safe-deploy init > safe-deploy.yaml
```

Does not touch the filesystem on its own.

## `safe-deploy status`

Show the current state of every configured app.

```bash
$ safe-deploy status

web  image=nginx:stable  active=green
  blue: exited  image=nginx:stable      id=a1b2c3d4
  green: running  image=nginx:1.27       id=e5f6g7h8 (active)

api  image=ghcr.io/acme/api:v1.2.0  active=blue
  blue: running  image=ghcr.io/acme/api:v1.2.0  id=...  (active)
  green: -
```

Reads container status directly from Docker — `state.json` is used only
to know which colour is "active".

## `safe-deploy up <app> [--tag TAG]`

Deploy `<app>`. Optionally override the image tag for this single deploy.
Common in CI:

```bash
safe-deploy up api --tag "$CI_COMMIT_TAG"
```

Behaviour:

1. Pull the image (fall back to local copy if pull fails).
2. Start the inactive colour with the new image.
3. Run the HTTP health check (per `healthcheck` config).
4. Swap the network alias and publish `host_port` on the new colour.
5. Stop the old colour (kept around for instant rollback).

Exit codes:

- `0` — deploy succeeded; new colour is now active.
- non-zero — deploy aborted. The previous active colour is still serving.

Aborts before the swap on:

- image not pullable AND not present locally;
- health check fails or times out;
- Docker API errors during candidate startup.

When an abort happens, the candidate container is force-removed so the
next attempt starts clean.

## `safe-deploy back <app>`

Roll `<app>` back to the previous colour.

```bash
safe-deploy back web
```

Requires a stopped previous colour to exist (the normal post-deploy
state). Errors clearly if the previous container has been removed.

Behaviour:

1. Start the inactive colour (the previous version).
2. Re-run the health check.
3. Swap the alias back.
4. Stop the now-inactive (formerly active) colour.

## `safe-deploy logs <app> [--color blue|green] [-n LINES]`

Tail container logs.

```bash
safe-deploy logs api                  # active colour, last 200 lines
safe-deploy logs api --color blue     # specific colour
safe-deploy logs api -n 1000          # more history
```

Internally calls `container.logs(tail=N)`, so it returns the last N lines
and exits — it does not follow.

If the requested colour has no container, prints `<no <colour>
container>` instead of erroring.

## `safe-deploy tui`

Launch the TUI explicitly. Equivalent to running `safe-deploy` with no
subcommand. Useful when you want to be unambiguous in shell aliases.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Generic error (unknown app, config not found, Docker unreachable, deploy/rollback failed) |
| 2 | Click usage error (bad flag, missing argument) |

## Using with CI

A typical GitHub Actions / GitLab CI step:

```yaml
- name: Deploy
  run: |
    safe-deploy up api --tag "${{ github.sha }}"
```

Some teams prefer a wrapper that captures the result for Slack/PagerDuty:

```bash
if safe-deploy up api --tag "$TAG"; then
  notify "✅ api deployed: $TAG"
else
  notify "🚨 api deploy failed; previous version still serving"
  exit 1
fi
```

Because failed deploys leave the previous version untouched, you can
safely retry: the next `up` will start a fresh candidate from scratch.

## Using with cron

For periodic redeploys (e.g. nightly cache-bust on `:latest` images):

```cron
0 3 * * * /usr/local/bin/safe-deploy up web >> /var/log/safe-deploy.log 2>&1
```

Make sure the cron user has Docker socket access.
