# TUI guide

The TUI is the primary front-end for day-to-day operations. It's built
with [Textual](https://textual.textualize.io/) and runs in any modern
terminal.

Launch it:

```bash
safe-deploy           # default: opens the TUI
safe-deploy tui       # equivalent, explicit
```

## Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ safe-deploy   config=…/safe-deploy.yaml   network=safe-deploy   …    │  ← status bar
├──────────────────────────────────┬───────────────────────────────────┤
│ Applications                      │ ┌ Actions ┬ Container logs ─────┐│
│ ┌────────┬───────────┬────────┐  │ │                                ││
│ │ App    │ Image     │ Active │  │ │ Deploy                         ││
│ │ web    │ nginx:…   │ blue   │  │ │  [tag input] [Deploy]          ││
│ │ api    │ acme/api… │ green  │  │ │  [Rollback] [Refresh]          ││
│ └────────┴───────────┴────────┘  │ │                                ││
│                                   │ │ Activity log                   ││
│                                   │ │  18:42:12 deploy web → green   ││
│                                   │ │  18:42:14 healthy ✓            ││
│                                   │ │  …                             ││
│                                   │ └────────────────────────────────┘│
├──────────────────────────────────┴───────────────────────────────────┤
│ ^d Deploy  ^b Rollback  ^r Refresh  ^l Logs  ^q Quit                 │  ← footer
└──────────────────────────────────────────────────────────────────────┘
```

The exact rendering depends on terminal size — Textual reflows
gracefully.

## Keybindings

| Key | Action |
|-----|--------|
| `d` | Deploy the selected app (uses the tag from the input box, or the configured default if blank) |
| `b` | Rollback the selected app |
| `r` | Refresh the apps table |
| `l` | Show the selected app's blue logs in the Container logs tab |
| `q` | Quit |

Buttons mirror the keybinds for mouse-friendly use.

## The applications table

Five columns:

| Column | Meaning |
|--------|---------|
| App | Name from `safe-deploy.yaml` |
| Image | Currently configured `image:tag` (this is the *next* deploy's image, not necessarily what's running) |
| Active | The colour currently serving traffic, or `none` |
| Blue | Status indicator with an `ACTIVE` marker if blue is the live colour |
| Green | Same, for green |

Status indicators:

- 🟢 `running` — container is up
- 🔴 `exited` — container is stopped (normal for the inactive colour)
- 🟡 `created`, `paused` — transient or unusual state
- ⚪ unknown / dim
- `—` — no container exists for that colour yet

The cursor row drives every action — selecting `web` and pressing `d`
deploys `web`. The selection auto-snaps to the first row on first launch.

The table auto-refreshes every 5 seconds; press `r` to force an immediate
refresh.

## The Actions tab

### Deploy panel

- **Tag input** — type a tag here to override the configured default for
  the next deploy. Leave blank to use whatever is in `safe-deploy.yaml`.
  The override applies for the in-memory session only; the YAML file is
  not modified.
- **Deploy button (`d`)** — kicks off `deploy()` in a background thread
  so the UI stays responsive. Progress is streamed into the activity
  log.
- **Rollback button (`b`)** — kicks off `rollback()` similarly.
- **Refresh button (`r`)** — repopulate the table.

### Activity log

Scrolling, syntax-highlighted log of every action the tool takes during
a deploy or rollback: pulling, starting containers, health-check
results, alias swaps, errors. Timestamps are local. The log persists for
the life of the session — it's the place to confirm what just happened.

Errors render in red; successes in green; informational lines in default
colour.

## The Container logs tab

A simple log viewer for the running containers themselves.

- **Blue logs / Green logs** buttons — show the last 300 lines of stdout
  for the chosen colour of the selected app.
- The view does not auto-tail — click again or press `l` to refresh.

Useful in two situations:

1. A deploy passed health checks but you want to eyeball the new
   container's startup logs.
2. The active colour is misbehaving and you want to peek at it before
   deciding whether to roll back.

## Workflows

### Routine deploy

1. Make sure `safe-deploy.yaml` is up to date (this typically lives in
   the same repo as the app, alongside its `Dockerfile`).
2. Run `safe-deploy`.
3. Highlight the app in the table.
4. (Optional) Type the new tag into the input.
5. Press `d`.
6. Watch the activity log scroll past `pulling…`, `starting…`,
   `healthy ✓`, `alias '<app>' → <colour>`.
7. Eyeball the Container logs tab for the new colour.

### Emergency rollback

1. Run `safe-deploy` (or switch to it if it's already open).
2. Highlight the misbehaving app.
3. Press `b`.
4. Watch the activity log: the previous colour is started, re-checked,
   and the alias swaps back. Total time: typically <5 seconds.

If the rollback fails (e.g. previous container was removed), the
activity log says so explicitly and the active colour is left untouched.

### Investigating a failed deploy

When you see `✗ deploy failed: …` in the activity log:

1. Note the reason — usually "health check timed out" or "image not
   available".
2. Switch to the Container logs tab and inspect the candidate's logs.
   (The candidate has already been removed if the deploy aborted; in that
   case check `docker logs` from your shell instead.)
3. Fix the underlying issue, then redeploy.

## Tips

- **Resize the terminal** — Textual reflows; the right pane shrinks
  gracefully.
- **Mouse works.** Click rows, click buttons, scroll the activity log
  with the wheel.
- **Multiple operators?** `safe-deploy` doesn't have locking. Don't run
  two deploys against the same app at once. The `exclusive=True`
  decorator prevents *one* TUI instance from racing itself, but two
  separate processes can still collide.
