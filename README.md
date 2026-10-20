# VerseVision STT

Listens to a sermon (Whisper, on the Mac), recognises spoken Bible references and verses read aloud, and puts the verses on the
ProPresenter output. It follows a passage as it is read, guesses the next verse early and confirms it, preloads the verses ahead into the
open presentation so they come up in a fraction of a second, picks the Bible version when it is said or clear from the wording, and
re-reads "Isaiah 42" as Isaiah 40:2 when the verse that follows says so.

The sermon-notes importer (documents to ProPresenter slides) is a separate project: [huntrw6/versevision](https://github.com/huntrw6/versevision).
The two share nothing on disk and can be installed, updated and removed independently.

## Install (macOS, Intel or Apple silicon)

```sh
uv build --wheel
sh scripts/install-macos.sh install dist/versevision_stt-*.whl     # the program: ~/.local/bin/versevision-stt
versevision-stt install                                            # helper apps + Whisper + Bible texts (first time: a few minutes)
versevision-stt doctor                                             # checks everything, including ProPresenter's network API
```

Remote Mac: `sh scripts/deploy-to-node.sh jpl-graphics-imac`.

`versevision-stt install` reuses a Whisper build left by the earlier combined install (it copies it and leaves the original alone); otherwise it
builds `whisper.cpp` with the flags that work on Intel Macs (no Accelerate/BLAS/Metal). macOS asks for Microphone access the first time
the listener app runs, and again each time it is rebuilt.

## Use

```sh
versevision-stt listen --dry-run     # log what it would show; nothing goes on screen
versevision-stt listen               # listen on Dante, show verses for 30 s after the speaker last touches them, add them to the open presentation
```

Options: `--device`, `--hold`, `--presentation NAME`, `--no-add`, `--preload N`, `--no-follow`, `--no-content`, `--engine apple`, `--model`, `--debug`.
Logs: one folder per run under `~/Library/Logs/versevision-stt/listen/`.

## Where things live (none of it is shared with the importer)

| What | STT | Importer |
| --- | --- | --- |
| Program | `~/.local/bin/versevision-stt` (uv tool `versevision-stt`) | `~/.local/bin/versevision` |
| Helpers, Whisper, models | `~/VerseVision-STT/` | `~/VerseVision-tools/vvdialog` |
| Bible texts | `~/Library/Application Support/versevision-stt/` | `~/Library/Application Support/versevision/` |
| Logs | `~/Library/Logs/versevision-stt/` | `~/Library/Logs/versevision/` |

Remove: `sh scripts/install-macos.sh uninstall [--purge]` (`--purge` also deletes Whisper, models, Bible texts and logs).

## Development

```sh
uv sync --extra dev
uv run pytest
```

`tests/score_listen.py` replays a recorded listening log and scores what was on screen against what was being read; the fixtures are
real logs from the church iMac.
