# 🚀 safe-deploy: The Complete Guide

`safe-deploy` is a single-host, single-operator tool designed for **blue-green Docker deployments**. By declaring your applications in a straightforward YAML file, the tool maintains two container instances per app, one **blue** and one **green**. It allows you to flip traffic from one to the other only after the new instance has passed an HTTP health check, ensuring zero-downtime releases.

It ships with two native interfaces powered by the exact same underlying deploy engine:

* **A Textual TUI** (`safe-deploy`) for interactive operations, featuring at-a-glance status, one-key deploy and rollback actions, and live logs.
* **A scriptable CLI** (`safe-deploy up`, `back`, `status`, `logs`) designed for CI runners, scripts, and cron jobs.

---

## 🧠 1. Overview & Philosophy

Most teams desire zero-downtime releases, but adopting Kubernetes, Nomad, or ECS solely for blue-green deployments carries a massive operational tax. `safe-deploy` exists to fill this gap for smaller setups.

**Who is this for?**

* Solo developers and small operations teams running production workloads on a single Docker host or VPS.
* Internal tooling owners who want reliable, scriptable releases on shared infrastructure without waking anyone up for on-call emergencies.
* Educators and learners who want to study a readable, end-to-end implementation of the blue-green pattern.

**Design Philosophy:**

1. **Boring beats clever.** The deployment path executes a sequence of standard Docker API calls that a human can easily read and reason about.
2. **One host, one operator.** There are no control-plane daemons, no role-based access controls, and no cluster state. Application state is simply stored in a JSON file at `~/.safe-deploy/state.json`.
3. **Default to safety.** If a health check fails, the swap aborts, the candidate is torn down, and the previous active colour continues serving traffic completely uninterrupted. Old colours are stopped but never immediately removed, ensuring a one-click rollback is always ready.

**What it does not do:**

`safe-deploy` deliberately avoids multi-host orchestration, scheduling, autoscaling, and canary deployments. If you need progressive traffic splitting, you need a service mesh, meaning you have outgrown this tool.

---

## ⚙️ 2. How It Works

The core mechanism of `safe-deploy` relies on the **blue-green deployment pattern** combined intelligently with **Docker network aliases**.

### 🔄 The Alias Swap

Instead of requiring an external reverse proxy like Traefik, Caddy, or Nginx to reload its configuration and drop connections, `safe-deploy` manipulates Docker's internal DNS.

For an app named `web`, both the blue and green containers join a shared bridge network (by default, named `safe-deploy`). The currently active container holds two aliases on this network:

* Its specific colour alias (e.g., `web-blue`), which is permanently attached.
* The **bare alias** (`web`), which is strictly held by the active colour.

When other services hit `http://web`, Docker's DNS resolves to the active container. During a deployment swap, `safe-deploy` disconnects both containers from the network, then reconnects them while moving the bare `web` alias to the new colour. For external traffic, the tool maps the configured `host_port` exclusively to the active container, leaving the inactive container strictly internal.

### ⏱️ The Deployment Timeline

When you deploy a new version (e.g., `safe-deploy up web --tag 1.4.2`), the engine executes the following steps:

1. Reads the state cache to find the currently active colour.
2. Pulls the new image from the registry.
3. Force-removes any stale inactive container to free up the container name.
4. Starts the new candidate container and attaches it to the network.
5. Polls the HTTP health check until a `200 OK` is returned or the timeout is reached. If this fails, the candidate is removed and the deploy aborts safely.
6. Disconnects both colours and reconnects them, attaching the bare alias to the new container.
7. Updates `state.json` to mark the new colour as active.
8. Stops the old container, keeping it around for instant rollbacks.

---

## 📥 3. Installation

**Prerequisites:**

* Python 3.10+
* A running Docker daemon accessible via standard SDK channels
* A modern terminal supporting 256-colour output for the TUI

**Install from source:**

```bash
git clone https://github.com/abdullahhrashid/safe-deploy.git safe-deploy
cd safe-deploy
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Verify the installation by running:

```bash
safe-deploy --version
```

You should also verify your user can talk to the Docker daemon:

```bash
python -c "import docker; print(docker.from_env().version()['Version'])"
```

---

## 🛠️ 4. Configuration (`safe-deploy.yaml`)

The tool reads a single YAML configuration file. It checks the `-c` flag path first, then `./safe-deploy.yaml`, and finally `~/.safe-deploy/config.yaml`. You can scaffold a starter template using:

```bash
safe-deploy init > safe-deploy.yaml
```

### 📋 Schema Definition

```yaml
network: safe-deploy

apps:
  - name: api
    image: ghcr.io/acme/api
    tag: v1.2.0
    container_port: 8080
    host_port: 8080
    env:
      ENVIRONMENT: production
    healthcheck:
      path: /healthz
      port: 8080
      interval_s: 1.0
      timeout_s: 60
      expect_status: 200
```

If your app does not require external access, omit `host_port`. Only the active container binds to it, preventing port collisions.

---

## 💻 5. Command Line Interface (CLI)

* `safe-deploy status`
  Prints the current state, image, and active colour of all configured apps.

* `safe-deploy up <app> [--tag TAG]`
  Deploys the application. Returns `0` on success and `1` if the deploy is aborted.

* `safe-deploy back <app>`
  Reverses the alias swap and routes traffic back to the previous version.

* `safe-deploy logs <app> [--color blue|green] [-n LINES]`
  Fetches the last `N` log lines for the specified container.

* `safe-deploy tui`
  Launches the Terminal User Interface.

---

## 🖥️ 6. Terminal User Interface (TUI)

Running `safe-deploy` with no arguments launches the TUI.

### 🧭 Layout & Navigation

The UI presents an Applications table, an Actions panel, and a live Activity Log.

**Keybindings:**

* `d`: Deploy the selected app
* `b`: Rollback the selected app
* `r`: Refresh status
* `l`: View logs
* `q`: Quit

### 🌊 Workflows

When you trigger a deployment, the task runs in a background thread to keep the UI responsive. Progress is streamed into the Activity Log in real time.

---

## 🏗️ 7. Architecture & Contributing

The codebase is compact, roughly 700 lines of Python.

* **`deploy.py`**: Core deploy, rollback, and health check logic
* **`DockerDriver`**: Thin abstraction over Docker API
* **`state.py`**: Manages `~/.safe-deploy/state.json`
* **Dependencies**: `textual`, `docker`, `pyyaml`, `click`

---

## 🚑 8. Troubleshooting

* **Docker connection error**: Ensure the daemon is running and permissions are correct
* **Image not available**: Check registry access and tag correctness
* **Health check failed**: Verify endpoint, port, and startup behavior
* **Port already allocated**: Another container is using the port
* **No rollback target**: No previous container exists

---

## ❓ 9. Frequently Asked Questions

**Why not docker-compose?**
`docker compose up -d` recreates containers in place, causing brief downtime. `safe-deploy` provides true zero-downtime swaps with instant rollback.

**Can I use multiple hosts?**
No. Each host runs independently.

**How do I handle database migrations?**
Use expand-and-contract migrations to maintain compatibility during deployment.

**What about WebSockets?**
Existing connections remain attached to the old container until they disconnect.

