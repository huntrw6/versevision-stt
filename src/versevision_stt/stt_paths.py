"""Where VerseVision STT keeps everything. It shares NOTHING with the VerseVision importer (huntrw6/versevision):

    program        uv tool "versevision-stt"             command: versevision-stt          (importer: "versevision")
    helpers        ~/VerseVision-STT/                    (importer: ~/VerseVision-tools)
    settings/data  <user data dir>/versevision-stt/      (importer: <user data dir>/versevision)
    logs           <user log dir>/versevision-stt/       (importer: <user log dir>/versevision)

so installing, updating or removing one can never touch the other. Environment overrides exist for tests and special setups:
VERSEVISION_STT_HOME, VERSEVISION_STT_DATA, VERSEVISION_STT_LOGS.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path, user_log_path

NAME = "versevision-stt"


def _env_path(var: str) -> Path | None:
    value = os.environ.get(var)
    return Path(value).expanduser() if value else None


@dataclass(frozen=True)
class Paths:
    home: Path          # helper apps, Whisper, models
    data: Path          # Bible texts
    logs: Path          # one folder per listening run

    @property
    def app(self) -> Path:
        return self.home / "VerseVision Listen.app"

    @property
    def app_binary(self) -> Path:
        return self.app / "Contents" / "MacOS" / "vvlisten"

    @property
    def vvadd(self) -> Path:
        return self.home / "vvadd"

    @property
    def vvbible(self) -> Path:
        return self.home / "vvbible"

    @property
    def vvdialog(self) -> Path:
        return self.home / "vvdialog"

    @property
    def whisper_dir(self) -> Path:
        return self.home / "whisper" / "whisper.cpp"

    @property
    def whisper_bin_dir(self) -> Path:
        return self.whisper_dir / "build" / "bin"

    @property
    def whisper_server(self) -> Path:
        return self.whisper_bin_dir / "whisper-server"

    @property
    def models_dir(self) -> Path:
        return self.whisper_dir / "models"

    def model_file(self, model: str) -> Path:
        return self.models_dir / f"ggml-{model}.bin"

    @property
    def scripture(self) -> Path:
        return self.data / "scripture"

    @property
    def stamp(self) -> Path:
        return self.home / ".build-stamp.json"


def paths() -> Paths:
    """Resolved at call time, so tests and environment overrides take effect."""
    return Paths(
        home=_env_path("VERSEVISION_STT_HOME") or Path.home() / "VerseVision-STT",
        data=_env_path("VERSEVISION_STT_DATA") or user_data_path(NAME),
        logs=_env_path("VERSEVISION_STT_LOGS") or user_log_path(NAME),
    )


@dataclass(frozen=True)
class LegacyPaths:
    """Where the listener lived while it was part of the importer (versevision 0.8 - 0.15)."""
    tools: Path
    scripture: Path
    logs: Path

    @property
    def app(self) -> Path:
        return self.tools / "VerseVision Listen.app"

    @property
    def whisper(self) -> Path:
        return self.tools / "whisper"


def legacy() -> LegacyPaths:
    return LegacyPaths(
        tools=Path.home() / "VerseVision-tools",
        scripture=user_data_path("versevision") / "scripture",
        logs=user_log_path("versevision") / "listen",
    )
