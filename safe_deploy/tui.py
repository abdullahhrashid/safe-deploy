from __future__ import annotations

import asyncio
from datetime import datetime

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from safe_deploy.config import Config
from safe_deploy.deploy import (
    DeployError,
    DockerDriver,
    all_apps,
    deploy,
    rollback,
)
from safe_deploy.state import State


def _fmt_color_cell(info: dict | None, is_active: bool) -> str:
    if info is None:
        return "[dim]—[/dim]"
    status = info.get("status") or "?"
    icon = {
        "running": "[green]●[/green]",
        "exited": "[red]●[/red]",
        "created": "[yellow]●[/yellow]",
        "paused": "[yellow]●[/yellow]",
    }.get(status, "[dim]●[/dim]")
    marker = "[bold cyan] ACTIVE[/bold cyan]" if is_active else ""
    return f"{icon} {status}{marker}"


class StatusPanel(Static):
    """Top status bar showing config + docker host."""

    def __init__(self, config_path: str, network: str, n_apps: int):
        super().__init__()
        self.config_path = config_path
        self.network = network
        self.n_apps = n_apps

    def render(self) -> str:
        return (
            f"[b]safe-deploy[/b]   "
            f"config=[cyan]{self.config_path}[/cyan]   "
            f"network=[magenta]{self.network}[/magenta]   "
            f"apps=[yellow]{self.n_apps}[/yellow]"
        )


class SafeDeployApp(App):
    CSS = """
    Screen { layout: vertical; }
    StatusPanel { height: 1; padding: 0 1; background: $boost; color: $text; }
    #apps-table { height: 1fr; }
    #right { width: 50%; }
    #left  { width: 50%; }
    #log { height: 1fr; border: tall $primary; }
    .row { height: auto; padding: 0 1; }
    Button { margin: 0 1; }
    Input { margin: 0 1; }
    Label.section { color: $accent; padding: 1 1 0 1; }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("d", "deploy", "Deploy"),
        Binding("b", "rollback", "Rollback"),
        Binding("l", "logs", "Logs"),
        Binding("q", "quit", "Quit"),
    ]

    selected_app: reactive[str | None] = reactive(None)

    def __init__(self, config: Config, state: State, driver: DockerDriver, config_path: str):
        super().__init__()
        self.config = config
        self.state = state
        self.driver = driver
        self.config_path = config_path

    # ---------- compose ----------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield StatusPanel(self.config_path, self.config.network, len(self.config.apps))
        with Horizontal():
            with Vertical(id="left"):
                yield Label("Applications", classes="section")
                table = DataTable(id="apps-table", cursor_type="row", zebra_stripes=True)
                table.add_columns("App", "Image", "Active", "Blue", "Green")
                yield table
            with Vertical(id="right"):
                with TabbedContent(initial="actions"):
                    with TabPane("Actions", id="actions"):
                        yield Label("Deploy", classes="section")
                        with Horizontal(classes="row"):
                            yield Input(placeholder="image tag (default: latest)", id="tag")
                            yield Button("Deploy", id="btn-deploy", variant="success")
                        with Horizontal(classes="row"):
                            yield Button("Rollback", id="btn-rollback", variant="warning")
                            yield Button("Refresh", id="btn-refresh")
                        yield Label("Activity log", classes="section")
                        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
                    with TabPane("Container logs", id="clogs"):
                        with Horizontal(classes="row"):
                            yield Button("Blue logs", id="btn-blue-logs")
                            yield Button("Green logs", id="btn-green-logs")
                        yield RichLog(id="container-log", highlight=False, markup=False, wrap=False)
        yield Footer()

    # ---------- lifecycle ----------
    def on_mount(self) -> None:
        self.title = "safe-deploy"
        self.sub_title = "blue/green for SMEs"
        self.refresh_table()
        self.set_interval(5.0, self.refresh_table)

    # ---------- helpers ----------
    @property
    def log_widget(self) -> RichLog:
        return self.query_one("#log", RichLog)

    @property
    def container_log_widget(self) -> RichLog:
        return self.query_one("#container-log", RichLog)

    def write_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_widget.write(f"[dim]{ts}[/dim] {msg}")

    def thread_log(self, msg: str) -> None:
        self.call_from_thread(self.write_log, msg)

    def current_spec(self):
        if self.selected_app is None:
            return None
        return self.config.apps.get(self.selected_app)

    # ---------- table ----------
    def refresh_table(self) -> None:
        table = self.query_one("#apps-table", DataTable)
        rows = all_apps(self.config.apps.values(), self.state, self.driver)
        # Preserve selection
        prior = self.selected_app
        table.clear()
        for ov in rows:
            active = ov["active"]
            table.add_row(
                ov["name"],
                ov["image"],
                f"[bold cyan]{active}[/bold cyan]" if active else "[dim]none[/dim]",
                _fmt_color_cell(ov["blue"], active == "blue"),
                _fmt_color_cell(ov["green"], active == "green"),
                key=ov["name"],
            )
        if prior is not None:
            try:
                table.move_cursor(row=list(self.config.apps.keys()).index(prior))
            except ValueError:
                pass
        elif rows:
            self.selected_app = rows[0]["name"]

    @on(DataTable.RowHighlighted, "#apps-table")
    def _on_row_highlight(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None and event.row_key.value is not None:
            self.selected_app = str(event.row_key.value)

    # ---------- actions ----------
    def action_refresh(self) -> None:
        self.refresh_table()
        self.write_log("[dim]refreshed[/dim]")

    def action_deploy(self) -> None:
        self._kick_deploy()

    def action_rollback(self) -> None:
        self._kick_rollback()

    def action_logs(self) -> None:
        self._show_logs("blue")

    @on(Button.Pressed, "#btn-deploy")
    def _btn_deploy(self) -> None:
        self._kick_deploy()

    @on(Button.Pressed, "#btn-rollback")
    def _btn_rollback(self) -> None:
        self._kick_rollback()

    @on(Button.Pressed, "#btn-refresh")
    def _btn_refresh(self) -> None:
        self.action_refresh()

    @on(Button.Pressed, "#btn-blue-logs")
    def _btn_blue_logs(self) -> None:
        self._show_logs("blue")

    @on(Button.Pressed, "#btn-green-logs")
    def _btn_green_logs(self) -> None:
        self._show_logs("green")

    def _kick_deploy(self) -> None:
        spec = self.current_spec()
        if spec is None:
            self.write_log("[red]no app selected[/red]")
            return
        tag = self.query_one("#tag", Input).value.strip()
        if tag:
            spec.tag = tag
        self.write_log(f"[bold]deploy[/bold] {spec.name} ({spec.image_ref})")
        self._run_deploy(spec)

    def _kick_rollback(self) -> None:
        spec = self.current_spec()
        if spec is None:
            self.write_log("[red]no app selected[/red]")
            return
        self.write_log(f"[bold]rollback[/bold] {spec.name}")
        self._run_rollback(spec)

    def _show_logs(self, color: str) -> None:
        spec = self.current_spec()
        if spec is None:
            return
        text = self.driver.tail_logs(spec.name, color, lines=300)  # type: ignore[arg-type]
        clog = self.container_log_widget
        clog.clear()
        clog.write(f"--- {spec.name} {color} ---\n{text}")

    # ---------- workers ----------
    @work(thread=True, exclusive=True, group="ops")
    def _run_deploy(self, spec) -> None:
        try:
            result = deploy(spec, self.state, self.driver, log=self.thread_log)
            self.thread_log(f"[green]✓[/green] {result.app} → {result.new_color}")
        except DeployError as exc:
            self.thread_log(f"[red]✗ deploy failed:[/red] {exc}")
        except Exception as exc:  # noqa: BLE001
            self.thread_log(f"[red]✗ error:[/red] {exc}")
        finally:
            self.call_from_thread(self.refresh_table)

    @work(thread=True, exclusive=True, group="ops")
    def _run_rollback(self, spec) -> None:
        try:
            result = rollback(spec, self.state, self.driver, log=self.thread_log)
            self.thread_log(f"[green]✓[/green] {result.app} rolled back to {result.new_color}")
        except DeployError as exc:
            self.thread_log(f"[red]✗ rollback failed:[/red] {exc}")
        except Exception as exc:  # noqa: BLE001
            self.thread_log(f"[red]✗ error:[/red] {exc}")
        finally:
            self.call_from_thread(self.refresh_table)


def run_tui(config: Config, state: State, driver: DockerDriver, config_path: str) -> None:
    SafeDeployApp(config, state, driver, config_path).run()
