from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Literal

Color = Literal["blue", "green"]
OTHER: dict[str, Color] = {"blue": "green", "green": "blue"}


def other(color: Color) -> Color:
    return OTHER[color]


class State:
    def __init__(self, path: Path):
        self.path = path
        self._lock = Lock()
        self._data: dict = {"apps": {}}
        if path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {"apps": {}}
        self._data.setdefault("apps", {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def active_color(self, app: str) -> Color | None:
        with self._lock:
            return self._data["apps"].get(app, {}).get("active")

    def set_active(self, app: str, color: Color, image_ref: str) -> None:
        with self._lock:
            entry = self._data["apps"].setdefault(app, {})
            entry["active"] = color
            entry.setdefault("colors", {})[color] = {"image": image_ref}
            self._save()

    def record_deployed(self, app: str, color: Color, image_ref: str) -> None:
        with self._lock:
            entry = self._data["apps"].setdefault(app, {})
            entry.setdefault("colors", {})[color] = {"image": image_ref}
            self._save()

    def info(self, app: str) -> dict:
        with self._lock:
            return dict(self._data["apps"].get(app, {}))


def default_state_path() -> Path:
    return Path.home() / ".safe-deploy" / "state.json"
