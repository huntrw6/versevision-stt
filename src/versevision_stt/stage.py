"""The staged Bible lookup: keep the verses the speaker is about to read pulled up in ProPresenter's Bible panel, ready to be put on screen
by a single click.

A lookup like "James 1:3-9" produces a row of result cards. Nothing is on the output until a card is clicked, and a click takes ~10-50 ms,
so while the speaker reads verse 3 the cards for 4, 5, 6 ... are already waiting. A verse that does not fit one slide becomes several cards
(same label, different text), so cards are identified by label AND text, and every click is checked against what ProPresenter reports live.

How the card list is learned: right after a fresh lookup the FIRST card is always the first part of the first verse, so it is safe to click
before anything is known. Once one card is live, the API lists every card of the set; from then on any card can be found by (chapter, verse,
part). Each later click is verified against the live slide and corrected once if it landed somewhere else.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable

from .slidemap import parse_slide


def lookup_name(book: str) -> str:
    """ProPresenter's lookup box wants "Psalm", not the printed name "Psalms"."""
    return re.sub(r"^Psalms\b", "Psalm", book)


@dataclass
class Card:
    chapter: int
    verse: int
    part: int            # 1-based position among the cards of this verse
    parts: int           # how many cards this verse has
    text: str            # the card's own words (without the "James 1:3 (ESV)" line)


@dataclass
class Window:
    """What the Bible panel currently shows."""
    book_id: str
    book: str
    chapter: int
    first: int
    last: int
    version: str                       # ProPresenter's name for the Bible version it was looked up in ("" = whatever was selected)
    cards: list[Card] | None = None    # None until one card has been put live and the API could list the set

    def index_of(self, chapter: int, verse: int, part: int = 1) -> int | None:
        """1-based card number, or None."""
        if self.cards is None:
            return 1 if (chapter == self.chapter and verse == self.first and part == 1) else None
        for i, c in enumerate(self.cards, 1):
            if c.chapter == chapter and c.verse == verse and c.part == part:
                return i
        return None

    def parts_of(self, chapter: int, verse: int) -> list[str]:
        return [c.text for c in (self.cards or []) if c.chapter == chapter and c.verse == verse]


def parse_cards(texts: list[str]) -> list[Card]:
    raw: list[tuple[str, int, int, str]] = []
    for t in texts:
        head, _, body = (t or "").partition("\n")
        hit = parse_slide(head)
        if hit is None:
            raw.append(("", 0, 0, t or ""))
            continue
        raw.append((hit[0], hit[1], hit[2], body.strip()))
    counts: dict[tuple[int, int], int] = {}
    for _b, c, v, _t in raw:
        counts[(c, v)] = counts.get((c, v), 0) + 1
    seen: dict[tuple[int, int], int] = {}
    out: list[Card] = []
    for _b, c, v, body in raw:
        seen[(c, v)] = seen.get((c, v), 0) + 1
        out.append(Card(c, v, seen[(c, v)], counts[(c, v)], body))
    return out


@dataclass
class Shown:
    ok: bool
    how: str = ""            # "click" (already staged) | "lookup" (had to look it up first) | "failed"
    ms: int = 0
    parts: list[str] = field(default_factory=list)
    note: str = ""


class Stage:
    def __init__(self, ui, chapter_size: Callable[[str, int], int], *, lookahead: int = 6, refill_at: int = 2,
                 live_slide: Callable[[], tuple[str, str]] | None = None, live_set: Callable[[], list[str]] | None = None,
                 log: Callable[[str], None] = lambda s: None, settle: float = 0.6):
        from .bibleui import live_set as _ls, live_slide as _lv
        self.ui = ui
        self.chapter_size = chapter_size          # (book_id, chapter) -> number of verses
        self.lookahead = lookahead
        self.refill_at = refill_at
        self.live_slide = live_slide or _lv
        self.live_set = live_set or _ls
        self.log = log
        self.settle = settle
        self.window: Window | None = None
        self.version = ""                         # the Bible version selected in ProPresenter, when we set it
        self.current: tuple[str, int, int, int] | None = None     # (book_id, chapter, verse, part) on the output

    # ------------------------------------------------------------------ what is staged
    def covers(self, book_id: str, chapter: int, verse: int, version: str = "", part: int = 1) -> bool:
        w = self.window
        if not w or w.book_id != book_id:
            return False
        if version and w.version and version != w.version:
            return False
        return w.index_of(chapter, verse, part) is not None

    def staged_verses(self) -> list[tuple[int, int]]:
        w = self.window
        return sorted({(c.chapter, c.verse) for c in (w.cards or [])}) if w else []

    def needs_refill(self) -> bool:
        w, cur = self.window, self.current
        if not w or not cur or w.book_id != cur[0] or cur[1] != w.chapter:
            return False
        size = self.chapter_size(w.book_id, w.chapter)
        return w.last < size and (w.last - cur[2]) < self.refill_at

    # ------------------------------------------------------------------ putting a verse on the output
    def show(self, book_id: str, book: str, chapter: int, verse: int, part: int = 1, *, version: str = "", range_end: tuple[int, int] | None = None) -> Shown:
        t0 = time.time()
        if version and version != self.version:
            r = self.ui.version(version)
            if r.get("ok"):
                self.version = version
                self.window = None                 # results from another Bible are stale
            else:
                self.log(f"            could not select '{version}' ({r.get('error', '?')}); left as it was")
        if self.covers(book_id, chapter, verse, version=self.version, part=part):
            res = self._click_and_check(book_id, chapter, verse, part)
            if res.ok:
                res.ms = int((time.time() - t0) * 1000)
                return res
            self.log(f"            ({res.note}); looking it up again")
        res = self._lookup_and_show(book_id, book, chapter, verse, part, range_end)
        res.ms = int((time.time() - t0) * 1000)
        return res

    def prepare(self, book_id: str, book: str, chapter: int, verse: int, *, version: str = "", range_end: tuple[int, int] | None = None) -> bool:
        """Look the verse (and the ones after it) up in the Bible search and leave the results waiting. Nothing goes on the output."""
        if version and version != self.version:
            r = self.ui.version(version)
            if r.get("ok"):
                self.version = version
                self.window = None
        size = self.chapter_size(book_id, chapter)
        last = min(size, verse + self.lookahead)
        if range_end and range_end[0] == chapter:
            last = max(last, min(size, range_end[1]))
        text = f"{lookup_name(book)} {chapter}:{verse}" + (f"-{last}" if last > verse else "")
        r = self.ui.lookup(text)
        if not r.get("ok"):
            return False
        self.window = Window(book_id, book, chapter, verse, last, self.version)
        return True

    def _lookup_and_show(self, book_id: str, book: str, chapter: int, verse: int, part: int, range_end: tuple[int, int] | None) -> Shown:
        size = self.chapter_size(book_id, chapter)
        last = min(size, verse + self.lookahead)
        if range_end and range_end[0] == chapter:
            last = max(last, min(size, range_end[1]))
        text = f"{lookup_name(book)} {chapter}:{verse}" + (f"-{last}" if last > verse else "")
        r = self.ui.lookup(text)
        if not r.get("ok"):
            return Shown(False, "failed", note=f"lookup failed: {r.get('error', '?')}")
        self.window = Window(book_id, book, chapter, verse, last, self.version)
        # the first card is the first part of the first verse: safe to click before anything is known
        r = self.ui.click(1)
        if not r.get("ok"):
            return Shown(False, "failed", note="click failed")
        if not self._landed(book_id, chapter, verse, 1):
            return Shown(False, "failed", note="the verse did not come up after the lookup")
        self._learn_cards()
        if part > 1:
            idx = self.window.index_of(chapter, verse, part) if self.window else None
            if idx:
                self.ui.click(idx)
                self._landed(book_id, chapter, verse, part)
        self.current = (book_id, chapter, verse, part)
        parts = self.window.parts_of(chapter, verse) if self.window else []
        return Shown(True, "lookup", parts=parts)

    def _click_and_check(self, book_id: str, chapter: int, verse: int, part: int) -> Shown:
        w = self.window
        assert w is not None
        idx = w.index_of(chapter, verse, part)
        if idx is None:
            return Shown(False, "failed", note="not staged")
        r = self.ui.click(idx)
        if r.get("ok") and self._landed(book_id, chapter, verse, part):
            self.current = (book_id, chapter, verse, part)
            if w.cards is None:
                self._learn_cards()                    # the first card of a prepared lookup is live: the API can now list the whole set
            return Shown(True, "click", parts=w.parts_of(chapter, verse))
        # landed somewhere else: re-read the set and find the right card by its text
        self._learn_cards()
        idx2 = w.index_of(chapter, verse, part) if self.window is w else None
        if idx2 and idx2 != idx:
            self.ui.click(idx2)
            if self._landed(book_id, chapter, verse, part):
                self.current = (book_id, chapter, verse, part)
                return Shown(True, "click", parts=w.parts_of(chapter, verse), note="corrected once")
        return Shown(False, "failed", note="the click did not bring up the right card")

    def _landed(self, book_id: str, chapter: int, verse: int, part: int) -> bool:
        """Did the card we asked for come up? Compares the live slide's reference (and, for a later part, its words)."""
        def ok() -> bool:
            cur, _ = self.live_slide()
            head, _, body = cur.partition("\n")
            hit = parse_slide(head)
            if hit is None or (hit[0], hit[1], hit[2]) != (book_id, chapter, verse):
                return False
            if part > 1 and self.window and self.window.cards:
                want = next((c for c in self.window.cards if (c.chapter, c.verse, c.part) == (chapter, verse, part)), None)
                if want and want.text[:24] and not body.strip().startswith(want.text[:24]):
                    return False
            return True
        end = time.time() + self.settle
        while time.time() < end:
            if ok():
                return True
            time.sleep(0.01)
        return False

    def _learn_cards(self) -> None:
        if not self.window:
            return
        cards = parse_cards(self.live_set())
        if cards and any(c.verse == self.window.first and c.chapter == self.window.chapter for c in cards):
            self.window.cards = cards

    # ------------------------------------------------------------------ keeping the set ahead of the speaker
    def refill(self) -> bool:
        """Re-stage the set starting at the verse that is on the output, so the verses after it are cards again. The card for the part that
        is live is clicked once more (same words, so nothing visibly changes) to make the API list the new set."""
        if not self.current or not self.window:
            return False
        book_id, chapter, verse, part = self.current
        size = self.chapter_size(book_id, chapter)
        last = min(size, verse + self.lookahead)
        if last <= verse:
            return False
        text = f"{lookup_name(self.window.book)} {chapter}:{verse}-{last}"
        r = self.ui.lookup(text)
        if not r.get("ok"):
            return False
        self.window = Window(book_id, self.window.book, chapter, verse, last, self.version)
        r = self.ui.click(part if part >= 1 else 1)       # verse's part p is card p of the new set (it starts at this verse)
        self._landed(book_id, chapter, verse, part)
        self._learn_cards()
        return self.window.cards is not None
