# Troubleshooting

A field guide to the failures you're most likely to hit. If something
isn't here, check the activity log in the TUI (or stdout from the CLI) —
the engine logs every step it takes.

## "could not connect to Docker"

```text
Error: could not connect to Docker: ...
```

`safe-deploy` calls `docker.from_env()` at startup. This works when:

- the Docker daemon is running, and
- the current user can talk to it (Linux: in the `docker` group;
  macOS/Windows: Docker Desktop is started; remote: `DOCKER_HOST` and
  TLS env vars are set correctly).

Reproduce outside `safe-deploy`:

```bash
python -c "import docker; print(docker.from_env().version()['Version'])"
```

If that errors, fix Docker access first.

## "config not found"

```text
Error: config not found: /home/.../safe-deploy.yaml
```

`safe-deploy` looks for `./safe-deploy.yaml` then
`~/.safe-deploy/config.yaml`. Create one with:

```bash
safe-deploy init > safe-deploy.yaml
```

Or pass a path explicitly: `safe-deploy -c /etc/safe-deploy/prod.yaml status`.

## "image not available: …"

```text
✗ deploy failed: image not available: ghcr.io/acme/api:v1.4.2
```

The image couldn't be pulled and isn't present locally either. Common
causes:

- **Typo in `image` or `tag`** — check the YAML.
- **Private registry, no credentials** — run `docker login <registry>`
  as the same user that runs `safe-deploy`.
- **Network outage** — if the image *is* present locally, `safe-deploy`
  uses it; the error means it's neither pullable nor cached.
- **Tag rolled back upstream** — happens when CI deletes a tag.

Verify manually: `docker pull <image>:<tag>`.

## "<app>: <colour> failed health check"

```text
✗ deploy failed: web: green failed health check
```

The candidate started but never returned `expect_status` from the
configured `path` within `timeout_s`. The candidate has already been
removed; the previous active colour is still serving.

Diagnose:

1. **Inspect the candidate's logs.** `safe-deploy` removed the
   container, so `docker logs` won't find it. Re-run the deploy with
   the TUI open and watch the **Container logs** tab; or temporarily
   start the image manually to see startup output:
   ```bash
   docker run --rm -it <image>:<tag>
   ```
2. **Verify the health endpoint.** Does the new version still serve
   200 on the configured `healthcheck.path`? Has the path moved?
3. **Increase `timeout_s`.** Cold-start-heavy apps (Java, big Node
   bundles) may need 60–120s.
4. **Check the port.** `healthcheck.port` defaults to `container_port`.
   If your app listens on `8080` but `container_port` is `80`, the
   check probes the wrong port.

## "no previous <colour> container to roll back to"

```text
✗ rollback failed: web: no previous green container to roll back to
```

Rollback requires the previous colour's container to still exist
(stopped, but present). It can be missing because:

- This is the very first deploy — there's no previous version.
- Someone ran `docker rm` against the stopped container.
- A second consecutive deploy already replaced the old colour. (Each
  deploy stops the old colour but only *removes* it on the next deploy
  in order to free its name.)

There's no in-tool recovery. Redeploy the previous tag instead:

```bash
safe-deploy up web --tag <previous-tag>
```

## Port already allocated

```text
✗ error: 500 Server Error … Bind for 0.0.0.0:8080 failed: port is already allocated
```

Another container — likely managed outside `safe-deploy` — is holding
the host port. `safe-deploy` only publishes the port on the active
colour, so the conflict isn't with itself. Find the offender:

```bash
docker ps --filter "publish=8080"
```

Either stop the other container or change `host_port` in the YAML.

## Network alias not resolving from another container

Symptom: container B does `curl http://web` and gets a connection
refused or DNS failure.

Checklist:

1. **Is B on the same network?** Run `docker inspect <B>` and confirm
   the `safe-deploy` network is in `NetworkSettings.Networks`.
2. **Is anything active?** `safe-deploy status` should show `active=blue`
   or `active=green`. `active=none` means no candidate has been
   promoted yet.
3. **Did the swap finish?** Look for `alias '<app>' → <colour>` in the
   activity log of the most recent deploy.
4. **Was the network recreated?** If `safe-deploy` was uninstalled and
   reinstalled, the network might exist but containers from before the
   recreate are attached to the old one. Stop and `up` again.

## TUI looks broken / characters render wrong

Textual relies on a modern terminal. If you see boxes-instead-of-borders
or coloured noise:

- Use Windows Terminal, iTerm2, Alacritty, Kitty, or GNOME Terminal —
  cmd.exe and very old terminals don't render correctly.
- Set `TERM=xterm-256color` if your terminal supports it but advertises
  something older.
- Use `--no-color` upstream tools, but don't disable colour in the
  terminal itself — the TUI uses ANSI heavily.

## Stale state

If `state.json` thinks an app is active but the containers tell a
different story (e.g. you `docker rm`'d things manually), the cleanest
recovery is:

```bash
# nuke managed containers
docker ps -a --filter "label=safe-deploy.app=<app>" -q | xargs -r docker rm -f

# wipe state for that app (or the whole file)
rm ~/.safe-deploy/state.json

# redeploy from scratch
safe-deploy up <app>
```

This is safe because `safe-deploy` never stores anything you can't
recreate from the YAML and the registry.

## "docker.errors.APIError: 409 Conflict … is already in use"

A previous container with the same name still exists. `safe-deploy`'s
`start_color` removes any pre-existing container of the target name,
but if you've manually created `safe-deploy_<app>_<colour>` outside
the tool, it'll collide. Remove it:

```bash
docker rm -f safe-deploy_<app>_<colour>
```

then retry the deploy.

## Two TUIs at once

Don't. The `exclusive=True` worker decorator only protects one process
from racing itself; two separate `safe-deploy` instances against the
same app can interleave swaps unpredictably. Pick one operator at a
time, or front the workflow with a CI pipeline so deploys serialize on
the runner.

## Getting more signal

The engine streams every step through the `log` callback. To capture
a complete trace from the CLI:

```bash
safe-deploy up web --tag 1.4.2 2>&1 | tee deploy.log
```

For the TUI, copy out of the activity-log pane (it's a real
`RichLog` widget — terminal-native copy works).
