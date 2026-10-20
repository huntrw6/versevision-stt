#!/bin/sh
# VerseVision STT on macOS: install, update or remove the PROGRAM. Everything lives in your home folder; no admin rights.
#   install/update:  sh install-macos.sh install  versevision_stt-*.whl
#   remove:          sh install-macos.sh uninstall [--purge]
#
# This installer is completely separate from the VerseVision importer's (huntrw6/versevision):
#   program   ~/.local/share/uv/tools/versevision-stt      command ~/.local/bin/versevision-stt   (importer: versevision)
#   helpers   ~/VerseVision-STT                            (importer: ~/VerseVision-tools, ~/VerseVision-backups)
#   data/logs <user data dir>/versevision-stt, <user log dir>/versevision-stt   (importer: .../versevision)
# `uv tool install` / `uninstall` act on the "versevision-stt" tool only, so installing, updating or removing either project never
# changes the other. After installing the program, `versevision-stt install` builds the helper apps and Whisper (a few minutes the
# first time; it reuses an earlier Whisper build when it finds one).
set -eu
export PATH="$HOME/.local/bin:$PATH"
cmd="${1:-}"; shift || true
case "$cmd" in
  install)
    wheel="${1:?usage: install-macos.sh install path/to/versevision_stt.whl}"
    command -v uv >/dev/null 2>&1 || { echo "Installing uv (Python tool manager) into ~/.local/bin ..."; curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh; }
    uv tool install --force --python 3.12 "$wheel"
    echo "Installed program: $(versevision-stt --version 2>/dev/null || echo ok)  ($HOME/.local/bin/versevision-stt)"
    echo "Now set up the helpers:  versevision-stt install"
    ;;
  uninstall)
    versevision-stt uninstall ${1:+"$1"} >/dev/null 2>&1 || true
    uv tool uninstall versevision-stt >/dev/null 2>&1 || true
    echo "Removed the VerseVision STT program${1:+ and its helpers, Whisper, Bible texts and logs}. The VerseVision importer was not touched."
    ;;
  *) echo "usage: install-macos.sh install WHEEL | uninstall [--purge]"; exit 2 ;;
esac
