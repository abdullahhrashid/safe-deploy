# safe-deploy documentation

Welcome. `safe-deploy` is a small CLI + TUI that brings **blue-green
deployments** to teams running Docker on one or two boxes — without making
them adopt Kubernetes first.

This folder is the project's full documentation. If you're new, read in this
order:

| # | Doc | What you'll learn |
|---|-----|-------------------|
| 1 | [Overview](./overview.md) | What the tool is, who it's for, the design philosophy |
| 2 | [How it works](./how-it-works.md) | The blue-green model and how the alias-swap delivers zero downtime |
| 3 | [Installation](./installation.md) | Prerequisites, install, sanity checks |
| 4 | [Getting started](./getting-started.md) | Your first deploy in ~5 minutes |
| 5 | [Configuration reference](./configuration.md) | Every field in `safe-deploy.yaml` |
| 6 | [CLI reference](./cli-reference.md) | All subcommands and flags |
| 7 | [TUI guide](./tui-guide.md) | Layout, keybinds, workflows |
| 8 | [Architecture](./architecture.md) | Code layout for contributors |
| 9 | [Troubleshooting](./troubleshooting.md) | Common failures and fixes |
| 10 | [FAQ](./faq.md) | Scope, comparisons, what's intentionally missing |

If you only have two minutes, read [Overview](./overview.md) and the **Quick
start** section of [Getting started](./getting-started.md).
