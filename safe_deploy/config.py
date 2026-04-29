from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULT_NETWORK = "safe-deploy"


@dataclass
class HealthCheck:
    path: str = "/"
    port: int | None = None
    interval_s: float = 1.0
    timeout_s: float = 30.0
    expect_status: int = 200


@dataclass
class AppSpec:
    name: str
    image: str
    tag: str = "latest"
    container_port: int = 80
    host_port: int | None = None
    env: dict[str, str] = field(default_factory=dict)
    network: str = DEFAULT_NETWORK
    healthcheck: HealthCheck = field(default_factory=HealthCheck)

    @property
    def image_ref(self) -> str:
        return f"{self.image}:{self.tag}"


@dataclass
class Config:
    apps: dict[str, AppSpec]
    network: str = DEFAULT_NETWORK

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        network = raw.get("network", DEFAULT_NETWORK)
        apps: dict[str, AppSpec] = {}
        for entry in raw.get("apps", []):
            hc_raw = entry.get("healthcheck", {}) or {}
            hc = HealthCheck(
                path=hc_raw.get("path", "/"),
                port=hc_raw.get("port"),
                interval_s=float(hc_raw.get("interval_s", 1.0)),
                timeout_s=float(hc_raw.get("timeout_s", 30.0)),
                expect_status=int(hc_raw.get("expect_status", 200)),
            )
            spec = AppSpec(
                name=entry["name"],
                image=entry["image"],
                tag=str(entry.get("tag", "latest")),
                container_port=int(entry.get("container_port", 80)),
                host_port=entry.get("host_port"),
                env=dict(entry.get("env", {}) or {}),
                network=entry.get("network", network),
                healthcheck=hc,
            )
            apps[spec.name] = spec
        return cls(apps=apps, network=network)


def default_config_path() -> Path:
    cwd = Path.cwd() / "safe-deploy.yaml"
    if cwd.exists():
        return cwd
    return Path.home() / ".safe-deploy" / "config.yaml"
