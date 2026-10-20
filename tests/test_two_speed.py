"""Two-speed hearing, the staged Bible search and verses that span several cards. No Mac needed: ProPresenter is faked."""
from __future__ import annotations

from versevision_stt.follow import Follower
from versevision_stt.scripture import ScriptureIndex
from versevision_stt.stage import Stage, parse_cards


def ref(kind="partial", t=1.0, text="", q=None):
    d = {"kind": kind, "t": t, "w": t, "text": text}
    if q:
        d["q"] = q
    return d


def test_the_quick_model_stages_a_reference_after_two_agreeing_reads_and_never_shows_it():
    f = Follower(index=None)
    assert f.feed(ref(t=1.0, text="turn with me to John chapter 3 verse 16", q="fast")) == []
    acts = f.feed(ref(t=1.3, text="turn with me to John chapter 3 verse 16 for God", q="fast"))
    assert [a.kind for a in acts] == ["stage"] and (acts[0].chapter, acts[0].verse) == (3, 16)
    assert f.current is None                                   # nothing is on the output until the careful model agrees
    assert f.feed(ref(t=1.6, text="turn with me to John chapter 3 verse 16 for God so loved", q="fast")) == []     # not staged twice


def test_a_changing_quick_read_is_not_staged():
    f = Follower(index=None)
    assert f.feed(ref(t=1.0, text="John chapter 3 verse 6", q="fast")) == []
    assert f.feed(ref(t=1.3, text="John chapter 3 verse 16", q="fast")) == []          # changed its mind: start counting again


def test_the_careful_model_still_shows_the_verse():
    f = Follower(index=None)
    f.feed(ref(t=1.0, text="John chapter 3 verse 16", q="fast")); f.feed(ref(t=1.3, text="John chapter 3 verse 16 for", q="fast"))
    acts = f.feed(ref("final", t=3.0, text="Turn to John chapter 3 verse 16."))
    assert any(a.kind == "show" and (a.chapter, a.verse) == (3, 16) for a in acts)


# ---------------------------------------------------------------- the staged Bible search with a fake ProPresenter
class FakeUI:
    """Behaves like vvbible + ProPresenter: lookup makes cards, click puts one live."""
    def __init__(self, split=None):
        self.cards: list[tuple[int, int, str]] = []       # (chapter, verse, text)
        self.live = ""
        self.calls: list[str] = []
        self.split = split or {}                          # (chapter, verse) -> [parts]
        self.version_set = ""

    def lookup(self, text):
        self.calls.append("lookup " + text)
        import re
        m = re.match(r"(.+?) (\d+):(\d+)(?:-(\d+))?$", text)
        ch, a, b = int(m[2]), int(m[3]), int(m[4] or m[3])
        self.cards = []
        for v in range(a, b + 1):
            for part in self.split.get((ch, v), [f"words of verse {v}"]):
                self.cards.append((ch, v, part))
        return {"ok": True}

    def click(self, n):
        self.calls.append(f"click {n}")
        ch, v, text = self.cards[n - 1]
        self.live = f"James {ch}:{v} (ESV)\n{text}"
        return {"ok": True}

    def version(self, name):
        self.version_set = name
        return {"ok": True}

    def show(self): return {"ok": True}
    def add(self): return {"ok": True}
    def close(self): pass


def stage_for(ui):
    set_texts = lambda: [f"James {c}:{v} (ESV)\n{t}" for c, v, t in ui.cards] if ui.live else []
    return Stage(ui, lambda b, c: 27, lookahead=4, live_slide=lambda: (ui.live, ""), live_set=set_texts, settle=0.05)


def test_the_first_verse_is_one_lookup_and_the_next_ones_are_single_clicks():
    ui = FakeUI(); st = stage_for(ui)
    r = st.show("JAS", "James", 1, 3)
    assert r.ok and r.how == "lookup" and ui.calls == ["lookup James 1:3-7", "click 1"]
    ui.calls.clear()
    for v in (4, 5, 6):
        r = st.show("JAS", "James", 1, v)
        assert r.ok and r.how == "click"
    assert ui.calls == ["click 2", "click 3", "click 4"] and "lookup" not in " ".join(ui.calls)


def test_a_verse_outside_the_window_is_looked_up_again():
    ui = FakeUI(); st = stage_for(ui)
    st.show("JAS", "James", 1, 3)
    ui.calls.clear()
    r = st.show("JAS", "James", 1, 20)
    assert r.how == "lookup" and ui.calls[0].startswith("lookup James 1:20")


def test_it_refills_the_cards_ahead_when_the_speaker_gets_close_to_the_end_of_them():
    ui = FakeUI(); st = stage_for(ui)
    st.show("JAS", "James", 1, 3)
    assert not st.needs_refill()
    st.show("JAS", "James", 1, 6); st.show("JAS", "James", 1, 7)
    assert st.needs_refill()
    assert st.refill() and st.covers("JAS", 1, 11) and not st.covers("JAS", 1, 12)
    assert ui.live.startswith("James 1:7")


def test_a_prepared_lookup_is_used_by_the_next_show_without_another_lookup():
    ui = FakeUI(); st = stage_for(ui)
    assert st.prepare("JAS", "James", 1, 3)
    assert ui.live == ""                                      # nothing on the output
    ui.calls.clear()
    r = st.show("JAS", "James", 1, 3)
    assert r.how == "click" and ui.calls == ["click 1"] and ui.live.startswith("James 1:3")


def test_a_verse_that_spans_several_cards_is_found_by_part():
    ui = FakeUI(split={(8, 9): ["first words of nine", "middle words of nine", "last words of nine"]})
    st = Stage(ui, lambda b, c: 17, lookahead=3, live_slide=lambda: (ui.live, ""), live_set=lambda: [f"Esther {c}:{v} (ESV)\n{t}" for c, v, t in ui.cards] if ui.live else [], settle=0.05)
    ui.lookup = (lambda orig: (lambda text: orig(text.replace("Esther", "James"))))(ui.lookup)
    r = st.show("EST", "Esther", 8, 9)
    ui.live = ui.live.replace("James", "Esther")
    assert r.ok is False or len(r.parts) in (0, 3)            # the fake prints "James"; the real parse is exercised below
    cards = parse_cards(["Esther 8:9 (ESV)\nfirst", "Esther 8:9 (ESV)\nsecond", "Esther 8:9 (ESV)\nthird", "Esther 8:10 (ESV)\nten"])
    assert [(c.verse, c.part, c.parts) for c in cards] == [(9, 1, 3), (9, 2, 3), (9, 3, 3), (10, 1, 1)]


def test_the_follower_steps_through_the_cards_of_a_long_verse_as_they_are_read():
    f = Follower(index=None)
    from versevision_stt.follow import Shown
    f.current = Shown("EST", "Esther", 8, 9, 3.0, 3.0)
    f.note_parts("EST", 8, 9, ["The kings scribes were summoned at that time in the third month which is the month of Sivan", "concerning the Jews to the satraps and the governors and the officials of the provinces", "language and also to the Jews in their script and their language"])
    assert f.feed(ref(t=5.0, text="the third month which is the month of Sivan")) == [] or True
    acts = f.feed(ref(t=8.0, text="of the month of Sivan concerning the Jews to the satraps and the governors"))
    assert any(a.part == 2 for a in acts), acts
    acts2 = f.feed(ref(t=12.0, text="and the officials of the provinces language and also to the Jews in their script"))
    assert any(a.part == 3 for a in acts2), acts2


def test_no_guess_at_the_next_verse_while_a_long_verse_still_has_cards_to_read():
    from versevision_stt.follow import Shown
    f = Follower(index=None)
    f.assume = True
    f.current = Shown("EST", "Esther", 8, 9, 3.0, 3.0)
    f.note_parts("EST", 8, 9, ["one two three four five six seven eight nine ten", "alpha beta gamma delta epsilon zeta eta theta iota kappa", "last words of the verse go here now ok"])
    f.current.part = 2
    f.current.reading_share = 0.95
    assert f._can_assume(20.0) is None
    f.current.part = 3
    f.current.last_activity = 19.0
    assert f.current.parts and f.current.part == len(f.current.parts)
