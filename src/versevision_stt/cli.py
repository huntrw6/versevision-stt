"""The `versevision-stt` command."""
from __future__ import annotations

import typer

from versevision_stt import __version__
from versevision_stt.install_cli import app as install_app
from versevision_stt.listen_cli import listen_command
from versevision_stt.toggle import shortcut_command, toggle_command

app = typer.Typer(help="Listen to the sermon and put the Bible verses on the ProPresenter output.", no_args_is_help=True, add_completion=False)
app.command("listen")(listen_command)
app.command("toggle")(toggle_command)
app.command("shortcut")(shortcut_command)
for _cmd in install_app.registered_commands:
    app.command(_cmd.name)(_cmd.callback)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"VerseVision STT {__version__}")
        raise typer.Exit()


@app.callback()
def main(version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show the version and exit")) -> None:
    pass
