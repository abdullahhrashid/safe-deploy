from __future__ import annotations

import sys
from pathlib import Path

import click

from safe_deploy import __version__
from safe_deploy.config import Config, default_config_path
from safe_deploy.deploy import DeployError, DockerDriver, app_overview, deploy, rollback
from safe_deploy.state import State, default_state_path


def _load(config_path: Path | None) -> tuple[Config, State, DockerDriver, Path]:
    cfg_path = config_path or default_config_path()
    if not cfg_path.exists():
        raise click.ClickException(
            f"config not found: {cfg_path}\n"
            "create one with: safe-deploy init > safe-deploy.yaml"
        )
    config = Config.load(cfg_path)
    state = State(default_state_path())
    try:
        driver = DockerDriver()
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(f"could not connect to Docker: {exc}") from exc
    return config, state, driver, cfg_path


@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-c", "--config", type=click.Path(path_type=Path), help="path to safe-deploy.yaml")
@click.version_option(__version__)
@click.pass_context
def main(ctx: click.Context, config: Path | None) -> None:
    """Blue-green Docker deployments with a TUI."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    if ctx.invoked_subcommand is None:
        # default: launch the TUI
        cfg, state, driver, path = _load(config)
        from safe_deploy.tui import run_tui
        run_tui(cfg, state, driver, str(path))


@main.command()
def init() -> None:
    """Print an example config to stdout."""
    sample = """\
network: safe-deploy

apps:
  - name: web
    image: nginx
    tag: stable
    container_port: 80
    host_port: 8080
    healthcheck:
      path: /
      timeout_s: 30
      expect_status: 200
    env:
      ENVIRONMENT: production
"""
    click.echo(sample)


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show status of all configured apps."""
    cfg, state, driver, _ = _load(ctx.obj.get("config_path"))
    for spec in cfg.apps.values():
        ov = app_overview(spec, state, driver)
        active = ov["active"] or "none"
        click.echo(f"\n{click.style(spec.name, bold=True)}  image={spec.image_ref}  active={active}")
        for color in ("blue", "green"):
            info = ov[color]
            if info is None:
                click.echo(f"  {color}: -")
            else:
                tag = " (active)" if active == color else ""
                click.echo(
                    f"  {color}: {info['status']}  image={info['image']}  id={info['id']}{tag}"
                )


@main.command()
@click.argument("app")
@click.option("--tag", help="override image tag")
@click.pass_context
def up(ctx: click.Context, app: str, tag: str | None) -> None:
    """Deploy APP (blue-green)."""
    cfg, state, driver, _ = _load(ctx.obj.get("config_path"))
    spec = cfg.apps.get(app)
    if spec is None:
        raise click.ClickException(f"unknown app: {app}")
    if tag:
        spec.tag = tag
    try:
        result = deploy(spec, state, driver, log=click.echo)
    except DeployError as exc:
        raise click.ClickException(str(exc)) from exc
    click.secho(f"deployed {result.app} → {result.new_color}", fg="green")


@main.command()
@click.argument("app")
@click.pass_context
def back(ctx: click.Context, app: str) -> None:
    """Rollback APP to its previous color."""
    cfg, state, driver, _ = _load(ctx.obj.get("config_path"))
    spec = cfg.apps.get(app)
    if spec is None:
        raise click.ClickException(f"unknown app: {app}")
    try:
        result = rollback(spec, state, driver, log=click.echo)
    except DeployError as exc:
        raise click.ClickException(str(exc)) from exc
    click.secho(f"rolled back {result.app} → {result.new_color}", fg="yellow")


@main.command()
@click.argument("app")
@click.option("--color", type=click.Choice(["blue", "green"]), default=None)
@click.option("-n", "--lines", default=200, show_default=True)
@click.pass_context
def logs(ctx: click.Context, app: str, color: str | None, lines: int) -> None:
    """Tail container logs for APP."""
    cfg, state, driver, _ = _load(ctx.obj.get("config_path"))
    if app not in cfg.apps:
        raise click.ClickException(f"unknown app: {app}")
    chosen = color or state.active_color(app) or "blue"
    click.echo(driver.tail_logs(app, chosen, lines=lines))  # type: ignore[arg-type]


@main.command()
def tui() -> None:
    """Launch the TUI explicitly."""
    cfg, state, driver, path = _load(None)
    from safe_deploy.tui import run_tui
    run_tui(cfg, state, driver, str(path))


if __name__ == "__main__":
    main()
