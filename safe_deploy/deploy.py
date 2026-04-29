from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable

import docker
from docker.errors import APIError, ImageNotFound, NotFound
from docker.models.containers import Container

from safe_deploy.config import AppSpec
from safe_deploy.state import Color, State, other


LogFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@dataclass
class DeployResult:
    app: str
    new_color: Color
    old_color: Color | None
    image_ref: str


class DeployError(RuntimeError):
    pass


class DockerDriver:
    """Wrapper around the docker SDK with the operations safe-deploy needs."""

    def __init__(self, client: docker.DockerClient | None = None):
        self.client = client or docker.from_env()

    def ensure_network(self, name: str) -> None:
        try:
            self.client.networks.get(name)
        except NotFound:
            self.client.networks.create(name, driver="bridge")

    def container_name(self, app: str, color: Color) -> str:
        return f"safe-deploy_{app}_{color}"

    def get_container(self, app: str, color: Color) -> Container | None:
        try:
            return self.client.containers.get(self.container_name(app, color))
        except NotFound:
            return None

    def pull(self, image_ref: str, log: LogFn = _noop) -> None:
        log(f"pulling {image_ref}…")
        try:
            self.client.images.pull(image_ref)
        except (APIError, ImageNotFound) as exc:
            try:
                self.client.images.get(image_ref)
                log(f"pull failed ({exc}); using local image")
            except ImageNotFound as inner:
                raise DeployError(f"image not available: {image_ref}") from inner

    def start_color(self, spec: AppSpec, color: Color, log: LogFn = _noop) -> Container:
        name = self.container_name(spec.name, color)
        existing = self.get_container(spec.name, color)
        if existing is not None:
            log(f"removing previous {color} container")
            try:
                existing.remove(force=True)
            except APIError as exc:
                raise DeployError(f"could not remove old {color}: {exc}") from exc

        host_port = spec.host_port if color == "blue" else None
        ports = {f"{spec.container_port}/tcp": host_port} if host_port is not None else None

        log(f"starting {color} from {spec.image_ref}")
        container = self.client.containers.run(
            spec.image_ref,
            name=name,
            detach=True,
            environment=spec.env,
            network=spec.network,
            network_aliases=[f"{spec.name}-{color}"],
            ports=ports,
            labels={
                "safe-deploy.app": spec.name,
                "safe-deploy.color": color,
                "safe-deploy.image": spec.image_ref,
            },
            restart_policy={"Name": "unless-stopped"},
        )
        return container

    def swap_alias(self, spec: AppSpec, new_color: Color, log: LogFn = _noop) -> None:
        """Make `new_color` the alias-target for `spec.name` on the network."""
        network = self.client.networks.get(spec.network)
        for color in ("blue", "green"):
            container = self.get_container(spec.name, color)  # type: ignore[arg-type]
            if container is None:
                continue
            try:
                network.disconnect(container, force=True)
            except APIError:
                pass
            aliases = [f"{spec.name}-{color}"]
            if color == new_color:
                aliases.append(spec.name)
                log(f"alias '{spec.name}' → {color}")
            network.connect(container, aliases=aliases)

    def stop_color(self, app: str, color: Color, log: LogFn = _noop) -> None:
        container = self.get_container(app, color)
        if container is None:
            return
        log(f"stopping {color}")
        try:
            container.stop(timeout=10)
        except APIError as exc:
            log(f"stop failed: {exc}")

    def remove_color(self, app: str, color: Color, log: LogFn = _noop) -> None:
        container = self.get_container(app, color)
        if container is None:
            return
        log(f"removing {color}")
        try:
            container.remove(force=True)
        except APIError as exc:
            log(f"remove failed: {exc}")

    def container_status(self, app: str, color: Color) -> dict | None:
        c = self.get_container(app, color)
        if c is None:
            return None
        c.reload()
        attrs = c.attrs or {}
        state = attrs.get("State", {})
        return {
            "id": c.short_id,
            "status": state.get("Status", "unknown"),
            "health": (state.get("Health") or {}).get("Status"),
            "image": (attrs.get("Config") or {}).get("Image"),
            "started_at": state.get("StartedAt"),
        }

    def tail_logs(self, app: str, color: Color, lines: int = 200) -> str:
        container = self.get_container(app, color)
        if container is None:
            return f"<no {color} container>"
        try:
            return container.logs(tail=lines).decode("utf-8", errors="replace")
        except APIError as exc:
            return f"<log error: {exc}>"


def _http_check(host: str, port: int, path: str, expect: int, timeout: float) -> bool:
    url = f"http://{host}:{port}{path if path.startswith('/') else '/' + path}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == expect
    except (urllib.error.URLError, socket.timeout, ConnectionError):
        return False


def wait_healthy(driver: DockerDriver, spec: AppSpec, color: Color, log: LogFn = _noop) -> bool:
    container = driver.get_container(spec.name, color)
    if container is None:
        return False
    container.reload()
    ip = (
        container.attrs.get("NetworkSettings", {})
        .get("Networks", {})
        .get(spec.network, {})
        .get("IPAddress")
    )
    if not ip:
        log("no IP yet; assuming healthy after short wait")
        time.sleep(2.0)
        return True

    hc = spec.healthcheck
    port = hc.port or spec.container_port
    deadline = time.monotonic() + hc.timeout_s
    log(f"health-checking http://{ip}:{port}{hc.path} (≤{hc.timeout_s:.0f}s)")
    while time.monotonic() < deadline:
        container.reload()
        if container.status not in ("running", "created"):
            log(f"container exited: status={container.status}")
            return False
        if _http_check(ip, port, hc.path, hc.expect_status, timeout=2.0):
            log("healthy ✓")
            return True
        time.sleep(hc.interval_s)
    log("health check timed out ✗")
    return False


def deploy(
    spec: AppSpec,
    state: State,
    driver: DockerDriver | None = None,
    log: LogFn = _noop,
) -> DeployResult:
    driver = driver or DockerDriver()
    driver.ensure_network(spec.network)

    active = state.active_color(spec.name)
    target: Color = "green" if active == "blue" else "blue"
    log(f"=== deploy {spec.name} :: {active or 'none'} → {target} ===")

    driver.pull(spec.image_ref, log=log)
    driver.start_color(spec, target, log=log)
    state.record_deployed(spec.name, target, spec.image_ref)

    if not wait_healthy(driver, spec, target, log=log):
        log("rolling back: removing unhealthy candidate")
        driver.remove_color(spec.name, target, log=log)
        raise DeployError(f"{spec.name}: {target} failed health check")

    driver.swap_alias(spec, target, log=log)
    state.set_active(spec.name, target, spec.image_ref)

    if active and active != target:
        driver.stop_color(spec.name, active, log=log)
        log(f"old {active} kept stopped for fast rollback")

    log(f"=== {spec.name} now serving from {target} ===")
    return DeployResult(app=spec.name, new_color=target, old_color=active, image_ref=spec.image_ref)


def rollback(
    spec: AppSpec,
    state: State,
    driver: DockerDriver | None = None,
    log: LogFn = _noop,
) -> DeployResult:
    driver = driver or DockerDriver()
    active = state.active_color(spec.name)
    if active is None:
        raise DeployError(f"{spec.name}: nothing to rollback (no active deployment)")
    target: Color = other(active)
    prev = driver.get_container(spec.name, target)
    if prev is None:
        raise DeployError(f"{spec.name}: no previous {target} container to roll back to")

    log(f"=== rollback {spec.name} :: {active} → {target} ===")
    if prev.status != "running":
        log(f"starting {target}")
        prev.start()
    if not wait_healthy(driver, spec, target, log=log):
        raise DeployError(f"{spec.name}: previous {target} is unhealthy")

    driver.swap_alias(spec, target, log=log)
    state.set_active(spec.name, target, prev.attrs.get("Config", {}).get("Image", "?"))
    driver.stop_color(spec.name, active, log=log)
    log(f"=== {spec.name} rolled back to {target} ===")
    return DeployResult(
        app=spec.name,
        new_color=target,
        old_color=active,
        image_ref=prev.attrs.get("Config", {}).get("Image", "?"),
    )


def app_overview(spec: AppSpec, state: State, driver: DockerDriver) -> dict:
    active = state.active_color(spec.name)
    return {
        "name": spec.name,
        "image": spec.image_ref,
        "active": active,
        "blue": driver.container_status(spec.name, "blue"),
        "green": driver.container_status(spec.name, "green"),
    }


def all_apps(specs: Iterable[AppSpec], state: State, driver: DockerDriver) -> list[dict]:
    return [app_overview(s, state, driver) for s in specs]
