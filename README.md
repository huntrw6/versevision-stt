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
versevision-stt listen               # listen on Dante; verses are pulled up in ProPresenter's Bible search and put on the output with one click (nothing is added to a presentation unless you pass --add)
```

Options: `--device`, `--hold`, `--add` (also save every shown verse into the open presentation), `--presentation NAME`, `--ahead N` (verses kept pulled up after the current one, default 6), `--fast/--no-fast`, `--fast-model`, `--no-follow`, `--no-content`, `--engine apple`, `--model`, `--debug`.
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

## How it shows a verse

Two Whisper models listen at once: a quick one (`base.en`, ~0.45 s) spots a spoken reference early, a careful one (`small.en`, ~0.8 s) confirms it.
The quick model only *pulls the verse up* in ProPresenter's Bible search; the careful model's confirmation (or the verse's own wording) then clicks the
result card, which takes ~0.1 s. The verses after it are already in the same search, so reading on is one click each, and the set is refilled when the
speaker gets within two verses of its end. A verse that did not fit one slide is several cards; the listener moves to the next card when the speaker
reaches its first words. Every click is checked against the slide ProPresenter reports live.
