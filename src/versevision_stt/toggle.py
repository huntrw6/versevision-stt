"""One button to start or stop the listener: `versevision-stt toggle`, plus a Desktop shortcut that runs it."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import typer

from versevision_stt.stt_paths import paths

APP_NAME = "VerseVision Listen.app"          # the helper app; not the shortcut
SHORTCUT_NAME = "Verse Listener.app"


def _run_dir() -> Path:
    d = paths().data / "run"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pidfile() -> Path:
    return _run_dir() / "listen.pid"


def running_pid() -> int | None:
    try:
        pid = int(_pidfile().read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def _notify(title: str, message: str) -> None:
    if sys.platform != "darwin":
        return
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def stop() -> bool:
    pid = running_pid()
    if pid is not None:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        for _ in range(40):
            if running_pid() is None:
                break
            time.sleep(0.1)
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except OSError:
                pass
    # the helpers belong to this program only (their paths are inside ~/VerseVision-STT)
    home = str(paths().home)
    subprocess.run(["pkill", "-f", f"{home}/"], capture_output=True)
    _pidfile().unlink(missing_ok=True)
    return pid is not None


def start(extra: list[str] | None = None) -> int:
    log = _run_dir() / "listen.out"
    exe = shutil.which("versevision-stt") or str(Path(sys.argv[0]).resolve())
    with open(log, "ab") as out:
        proc = subprocess.Popen([exe, "listen", *(extra or [])], stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True)
    _pidfile().write_text(str(proc.pid))
    return proc.pid


def toggle_command(
    status: bool = typer.Option(False, "--status", help="Only say whether the listener is running"),
    on: bool = typer.Option(False, "--on", help="Start it (does nothing if it is already running)"),
    off: bool = typer.Option(False, "--off", help="Stop it"),
    quiet: bool = typer.Option(False, "--quiet", help="No notification"),
) -> None:
    """Start the listener if it is stopped, stop it if it is running (what the Desktop button does)."""
    pid = running_pid()
    if status:
        typer.echo("listening" if pid else "stopped")
        raise typer.Exit(0 if pid else 1)
    want_on = on or (not off and pid is None)
    if want_on:
        if pid:
            typer.echo(f"Already listening (pid {pid})")
            return
        new = start()
        typer.echo(f"Listening started (pid {new}). Output: {_run_dir() / 'listen.out'}")
        if not quiet:
            _notify("Verse Listener", "ON: listening for Bible verses")
    else:
        was = stop()
        typer.echo("Listening stopped" if was else "It was not running")
        if not quiet:
            _notify("Verse Listener", "OFF")


def shortcut_command(
    where: Path = typer.Option(Path("~/Desktop"), "--where", help="Folder to put the button in"),
    remove: bool = typer.Option(False, "--remove", help="Delete the button"),
) -> None:
    """Put a "Verse Listener" button on the Desktop: click it to start listening, click again to stop."""
    folder = where.expanduser()
    target = folder / SHORTCUT_NAME
    if remove:
        shutil.rmtree(target, ignore_errors=True)
        typer.echo(f"Removed {target}")
        return
    exe = shutil.which("versevision-stt") or str(Path.home() / ".local/bin/versevision-stt")
    src = f'''-- Verse Listener: click to start listening for Bible verses, click again to stop.
on run
    try
        do shell script "PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin; {exe} toggle >/dev/null 2>&1"
    on error msg
        display dialog "Verse Listener could not start: " & msg buttons {{"OK"}} default button 1
    end try
end run
'''
    tmp = paths().data / "run" / "toggle.applescript"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(src)
    shutil.rmtree(target, ignore_errors=True)
    res = subprocess.run(["osacompile", "-o", str(target), str(tmp)], capture_output=True, text=True)
    if res.returncode != 0:
        typer.secho(f"Could not build the button: {res.stderr.strip()}", fg="red")
        raise typer.Exit(1)
    # a plain applet that quits right after it runs (no Dock bounce left behind)
    subprocess.run(["defaults", "write", str(target / "Contents" / "Info"), "LSUIElement", "-bool", "true"], capture_output=True)
    subprocess.run(["codesign", "--force", "--sign", "-", str(target)], capture_output=True)
    typer.echo(f"Button created: {target}")
