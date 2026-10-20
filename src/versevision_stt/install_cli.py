"""`versevision-stt install | update | doctor | uninstall`: set up everything the listener needs, in its own folders.

Nothing here reads, changes or deletes anything that belongs to the VerseVision importer (huntrw6/versevision): not its program, its
settings, its `~/VerseVision-tools` helpers or its logs. The two can be installed, updated and removed in any order.

What `install` makes under ~/VerseVision-STT :
    VerseVision Listen.app   the audio listener (signed ad-hoc so macOS shows the Microphone prompt)
    vvadd                    types a reference into ProPresenter's Bible lookup and presses the buttons
    vvdialog                 answers a ProPresenter permission box when asked
    whisper/whisper.cpp/     Whisper speech recognition (built here) and its model files
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from importlib import resources
from pathlib import Path
from typing import Annotated, Callable

import typer

from versevision_stt import __version__
from versevision_stt.stt_paths import Paths, legacy, paths

WHISPER_REPO = "https://github.com/ggml-org/whisper.cpp.git"
WHISPER_REF = "0c7be696371069e0baa2515ed7aa08d5a5473aa6"      # the commit the listener was tuned and tested on
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin"
MODELS = ("small.en", "base.en", "medium.en")
BUNDLE_ID = "org.versevision.stt.listen"

app = typer.Typer(help="Install, update, check or remove the VerseVision STT helpers.", no_args_is_help=True)


# ----------------------------------------------------------------------------- small helpers
def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None, timeout: float = 3600, log: Callable[[str], None] = print) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        tail = "\n".join((res.stdout + res.stderr).strip().splitlines()[-12:])
        raise RuntimeError(f"{' '.join(cmd[:3])} failed ({res.returncode}):\n{tail}")
    return res


def _source(name: str) -> Path:
    return Path(str(resources.files("versevision_stt") / "node" / name))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else ""


def _read_stamp(p: Paths) -> dict:
    try:
        return json.loads(p.stamp.read_text())
    except Exception:
        return {}


def _write_stamp(p: Paths, data: dict) -> None:
    p.home.mkdir(parents=True, exist_ok=True)
    p.stamp.write_text(json.dumps(data, indent=2))


def _is_intel_mac() -> bool:
    return sys.platform == "darwin" and platform.machine() in {"x86_64", "AMD64"}


def _require_mac() -> None:
    if sys.platform != "darwin":
        typer.secho("The listener apps are macOS-only (they use Core Audio and the macOS accessibility API).", fg="red")
        raise typer.Exit(2)


# ----------------------------------------------------------------------------- the pieces
def build_swift(p: Paths, log: Callable[[str], None] = print, *, force: bool = False) -> list[str]:
    """Compile the Swift programs. Skipped when the source has not changed since the last build. Returns what was rebuilt."""
    if shutil.which("swiftc") is None:
        raise RuntimeError("swiftc was not found. Install Apple's command line tools:  xcode-select --install")
    stamp = _read_stamp(p)
    built = stamp.get("swift", {})
    rebuilt: list[str] = []
    p.home.mkdir(parents=True, exist_ok=True)
    for name, outputs in (("vvadd", p.vvadd), ("vvbible", p.vvbible), ("vvdialog", p.vvdialog), ("vvlisten", p.app_binary)):
        src = _source(f"{name}.swift")
        digest = _sha(src)
        if not force and built.get(name) == digest and outputs.exists():
            continue
        log(f"  building {name} ...")
        outputs.parent.mkdir(parents=True, exist_ok=True)
        tmp = outputs.with_name(outputs.name + ".new")
        _run(["swiftc", "-O", "-o", str(tmp), str(src)], log=log)
        os.replace(tmp, outputs)
        built[name] = digest
        rebuilt.append(name)
    if "vvlisten" in rebuilt or not (p.app / "Contents" / "Info.plist").exists():
        plist = (p.app / "Contents" / "Info.plist")
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(_source("vvlisten.plist").read_text().replace("org.versevision.listen", BUNDLE_ID).replace("VerseVision Listen", "VerseVision STT Listen"))
        _run(["codesign", "--force", "--sign", "-", str(p.app)], log=log)
        _run(["xattr", "-cr", str(p.app)], log=log)
        if "vvlisten" not in rebuilt:
            rebuilt.append("vvlisten")
    stamp["swift"] = built
    _write_stamp(p, stamp)
    return rebuilt


def build_whisper(p: Paths, log: Callable[[str], None] = print, *, force: bool = False) -> bool:
    """Fetch and build whisper.cpp. The flags matter: on an Intel iMac Pro the default build (Accelerate/BLAS, AVX512) produced
    garbage ("this this this"), so those are switched off, and Metal is off because the GPU is not used."""
    if p.whisper_server.exists() and not force:
        if _build_is_safe(p.whisper_dir / "build"):
            return False
        log("  the existing Whisper build uses the GPU/Accelerate paths that fail on this Mac; rebuilding it")
    for tool in ("git", "cmake"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} was not found. Install it first (git: xcode-select --install; cmake: pip/uv tool install cmake, or brew install cmake).")
    p.whisper_dir.parent.mkdir(parents=True, exist_ok=True)
    if not (p.whisper_dir / ".git").exists():
        log("  downloading whisper.cpp ...")
        _run(["git", "clone", "-q", WHISPER_REPO, str(p.whisper_dir)], log=log)
    _run(["git", "fetch", "-q", "origin"], cwd=p.whisper_dir, log=log)
    _run(["git", "checkout", "-q", WHISPER_REF], cwd=p.whisper_dir, log=log)
    flags = ["-DCMAKE_BUILD_TYPE=Release", "-DWHISPER_BUILD_SERVER=ON", "-DBUILD_SHARED_LIBS=ON", "-DGGML_METAL=OFF", "-DGGML_BLAS=OFF", "-DGGML_ACCELERATE=OFF"]
    if _is_intel_mac():
        flags += ["-DGGML_AVX512=OFF", "-DGGML_NATIVE=ON"]
    log("  building whisper.cpp (a few minutes) ...")
    _run(["cmake", "-S", str(p.whisper_dir), "-B", str(p.whisper_dir / "build"), *flags], log=log)
    _run(["cmake", "--build", str(p.whisper_dir / "build"), "--config", "Release", "-j", str(os.cpu_count() or 4), "--target", "whisper-server"], log=log)
    if not p.whisper_server.exists():
        raise RuntimeError("whisper-server was not produced by the build")
    return True


def fetch_model(p: Paths, model: str, log: Callable[[str], None] = print) -> bool:
    target = p.model_file(model)
    if target.exists() and target.stat().st_size > 10_000_000:
        return False
    import httpx
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    log(f"  downloading the {model} Whisper model ...")
    with httpx.stream("GET", MODEL_URL.format(model=model), follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.iter_bytes(1 << 20):
                fh.write(chunk)
    os.replace(tmp, target)
    return True


def fetch_bibles(log: Callable[[str], None] = print) -> None:
    from versevision_stt.scripture import download
    download(log=log)


def _build_is_safe(build_dir: Path) -> bool:
    """A Whisper build is only reused if it does not use the GPU/Accelerate code paths. On an Intel iMac Pro those produced garbage
    ("this this this"); the tuned build links neither Metal nor BLAS."""
    server = build_dir / "bin" / "whisper-server"
    if not server.exists():
        return False
    if sys.platform != "darwin":
        return True
    res = subprocess.run(["otool", "-L", str(server)], capture_output=True, text=True)
    linked = res.stdout.lower()
    return "metal" not in linked and "blas" not in linked and "accelerate" not in linked


def migrate_from_importer(p: Paths, log: Callable[[str], None] = print) -> list[str]:
    """Reuse what the old combined install already built (Whisper is ~2 GB), without changing the old folders: files are COPIED
    (cloned with copy-on-write on APFS) into the new home. The importer's own folders are never modified."""
    old = legacy()
    done: list[str] = []
    src = old.whisper / "whisper.cpp"
    if not p.whisper_dir.exists() and src.exists():
        good = next((v for v in ("build2", "build") if _build_is_safe(src / v)), None)
        if good is None:
            log("  the earlier Whisper build is not the right kind for this Mac; it will be built fresh")
        else:
            log("  found Whisper from the earlier combined install; copying it (the original is left alone) ...")
            p.whisper_dir.parent.mkdir(parents=True, exist_ok=True)
            cp = ["cp", "-cR"] if sys.platform == "darwin" else ["cp", "-R"]
            res = subprocess.run([*cp, str(src), str(p.whisper_dir)], capture_output=True, text=True)
            if res.returncode != 0:
                shutil.rmtree(p.whisper_dir, ignore_errors=True)
                shutil.copytree(src, p.whisper_dir, symlinks=True)
            target = p.whisper_dir / "build"
            if good == "build2":
                if target.is_symlink() or target.exists():
                    shutil.rmtree(target, ignore_errors=True) if target.is_dir() and not target.is_symlink() else target.unlink()
                os.symlink("build2", target)                     # the tuned build answers to the new folder name
            done.append("whisper")
    if old.scripture.exists() and not p.scripture.exists():
        p.scripture.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(old.scripture, p.scripture)
        done.append("bible texts")
    return done


# ----------------------------------------------------------------------------- commands
@app.command("install")
def install_command(
    model: Annotated[str, typer.Option("--model", help="Whisper model to download")] = "small.en",
    force: Annotated[bool, typer.Option("--force", help="Rebuild everything even if it looks up to date")] = False,
    no_whisper: Annotated[bool, typer.Option("--no-whisper", help="Skip Whisper (use the Apple recogniser only)")] = False,
) -> None:
    """Build the helper apps and set up Whisper. Safe to run again: it only redoes what changed."""
    _require_mac()
    p = paths()
    typer.echo(f"Installing VerseVision STT {__version__} into {p.home}")
    typer.echo("(the VerseVision importer, if installed, is not touched)")
    try:
        for what in migrate_from_importer(p, typer.echo):
            typer.echo(f"  reused {what}")
        rebuilt = build_swift(p, typer.echo, force=force)
        typer.echo("  helper apps: " + (", ".join(rebuilt) + " rebuilt" if rebuilt else "up to date"))
        if not no_whisper:
            typer.echo("  whisper: " + ("built" if build_whisper(p, typer.echo, force=force) else "already built"))
            for m in dict.fromkeys([model, "base.en"]):          # base.en is the quick model of the two-speed hearing
                typer.echo(f"  model {m}: " + ("downloaded" if fetch_model(p, m, typer.echo) else "already there"))
        fetch_bibles(typer.echo)
    except Exception as exc:
        typer.secho(f"Install stopped: {exc}", fg="red")
        raise typer.Exit(1)
    typer.secho("Done. Check it with:  versevision-stt doctor", fg="green")
    if "vvlisten" in (rebuilt if 'rebuilt' in dir() else []):
        typer.echo("The listener app was rebuilt, so macOS will ask for Microphone access once more the next time it starts.")


@app.command("update")
def update_command() -> None:
    """Rebuild whatever changed after upgrading the program (same as install, quicker to remember)."""
    install_command(model="small.en", force=False, no_whisper=False)


@app.command("doctor")
def doctor_command() -> None:
    """Check that everything the listener needs is in place."""
    p = paths()
    rows: list[tuple[str, bool, str]] = []
    rows.append(("macOS", sys.platform == "darwin", platform.platform()))
    rows.append(("listener app", p.app_binary.exists(), str(p.app)))
    rows.append(("vvbible (ProPresenter Bible control)", p.vvbible.exists(), str(p.vvbible)))
    rows.append(("vvadd (one-shot lookup)", p.vvadd.exists(), str(p.vvadd)))
    rows.append(("vvdialog", p.vvdialog.exists(), str(p.vvdialog)))
    rows.append(("whisper-server", p.whisper_server.exists(), str(p.whisper_server)))
    rows.append(("whisper model small.en", p.model_file("small.en").exists(), str(p.model_file("small.en"))))
    rows.append(("Bible texts", (p.scripture / "KJV.json").exists() and (p.scripture / "BSB.json").exists(), str(p.scripture)))
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:1025/version", timeout=3)
        rows.append(("ProPresenter network API", r.status_code == 200, "http://127.0.0.1:1025"))
    except Exception as exc:
        rows.append(("ProPresenter network API", False, f"not reachable ({type(exc).__name__}); open ProPresenter and enable its Network API on port 1025"))
    from versevision_stt.scripture import propresenter_bibles_dir
    n = len(list(propresenter_bibles_dir().glob("*.rvbible"))) if propresenter_bibles_dir().exists() else 0
    rows.append(("ProPresenter Bibles for wording match", n > 0, f"{n} installed"))
    bad = 0
    for name, ok, detail in rows:
        typer.echo(f"  {'ok ' if ok else 'MISSING'}  {name:40} {detail}")
        bad += 0 if ok else 1
    typer.echo("The importer's folders are separate and not checked here.")
    raise typer.Exit(1 if bad else 0)


@app.command("uninstall")
def uninstall_command(purge: Annotated[bool, typer.Option("--purge", help="Also delete the Whisper build and models (about 2 GB), Bible texts and logs")] = False) -> None:
    """Remove the listener's helper apps. The VerseVision importer is never touched."""
    p = paths()
    subprocess.run(["pkill", "-f", "VerseVision STT Listen.app"], capture_output=True)
    subprocess.run(["pkill", "-f", "whisper-server"], capture_output=True)
    removed = []
    shutil.rmtree(Path.home() / "Desktop" / "Verse Listener.app", ignore_errors=True)
    for target in (p.app, p.vvadd, p.vvbible, p.vvdialog, p.stamp):
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True); removed.append(target.name)
        elif target.exists():
            target.unlink(); removed.append(target.name)
    if purge:
        for target in (p.home, p.data, p.logs):
            if target.exists():
                shutil.rmtree(target, ignore_errors=True); removed.append(str(target))
    else:
        typer.echo(f"Kept Whisper, its models, the Bible texts and the logs (use --purge to remove them: {p.home}).")
    typer.echo("Removed: " + (", ".join(removed) or "nothing"))
    typer.echo("To remove the command itself:  uv tool uninstall versevision-stt")
