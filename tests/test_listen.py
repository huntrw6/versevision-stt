from versevision_stt.listen import Detector, run
from versevision_stt.references.spoken import find_spoken_references


def refs(text):
    return [r.text for r in find_spoken_references(text)]


def test_spoken_forms_become_written_references():
    assert refs("turn with me to John chapter three verse sixteen") == ["John 3:16"]
    assert refs("first Corinthians thirteen four") == ["1 Corinthians 13:4"]
    assert refs("Romans eight twenty eight") == ["Romans 8:28"]
    assert refs("Psalm twenty three one through three") == ["Psalms 23:1-3"]
    assert refs("Psalm one nineteen one oh five") == ["Psalms 119:105"]
    assert refs("Jude twenty four") == ["Jude 1:24"]
    assert refs("Ephesians two eight through nine") == ["Ephesians 2:8-9"]
    assert refs("John 3:16") == ["John 3:16"]


def test_ordinary_talk_never_triggers():
    for line in ["we have ten minutes and chapter three is next", "in the second chapter he said",
                 "the first time I read Acts it was two thousand", "verse sixteen is the key", "chapter three"]:
        assert refs(line) == [], line


def test_two_references_in_one_breath_keep_their_order():
    assert refs("John three sixteen and then Romans eight twenty eight") == ["John 3:16", "Romans 8:28"]


def stream(*items):
    return [{"kind": k, "t": t, "text": x} for k, t, x in items]


def test_a_reference_is_acted_on_once_after_it_settles_even_though_partials_repeat():
    shown = []
    found = run(stream(("partial", 1.0, "turn to John"), ("partial", 1.3, "turn to John three"), ("partial", 1.6, "turn to John three sixteen"),
                       ("partial", 2.0, "turn to John three sixteen and"), ("partial", 2.4, "turn to John three sixteen and we see"),
                       ("final", 3.0, "turn to John three sixteen and we see")),
                show=lambda r: shown.append(r) or True, log=lambda s: None)
    assert shown == ["John 3:16"] and [d.action for d in found] == ["shown"]


def test_a_half_heard_reference_that_changes_is_not_shown_early():
    shown = []
    run(stream(("partial", 1.0, "John three"), ("partial", 1.2, "John three sixteen"), ("partial", 1.4, "John three sixteen"),
               ("partial", 2.1, "John three sixteen"), ("final", 2.2, "John three sixteen")),
        show=lambda r: shown.append(r) or True, log=lambda s: None)
    assert shown == ["John 3:16"]            # not "John 3:1" or twice


def test_the_same_reference_inside_the_cooldown_is_skipped_but_a_later_one_is_shown():
    shown = []
    found = run(stream(("final", 1.0, "John three sixteen"), ("final", 10.0, "again John three sixteen"), ("final", 50.0, "John three sixteen once more")),
                show=lambda r: shown.append(r) or True, detector=Detector(cooldown=30), log=lambda s: None)
    assert shown == ["John 3:16", "John 3:16"] and [d.action for d in found] == ["shown", "skipped-repeat", "shown"]


def test_dry_run_shows_nothing():
    found = run(stream(("final", 1.0, "Romans eight twenty eight")), show=None, log=lambda s: None)
    assert [d.reference for d in found] == ["Romans 8:28"] and found[0].action == "logged"


def test_a_failed_show_is_reported_not_hidden():
    found = run(stream(("final", 1.0, "Romans eight twenty eight")), show=lambda r: False, log=lambda s: None)
    assert found[0].action == "show-failed"


def test_what_apple_speech_recognition_really_writes_is_understood():
    """Captured from the iMac: numbers come back as digits, and 'eight twenty eight' arrives as 828."""
    heard = "Turn with me to John chapter 3 verse 16 now look at Romans 828 and then first Corinthians 13 four Psalm 119 105"
    assert refs(heard) == ["John 3:16", "Romans 8:28", "1 Corinthians 13:4", "Psalms 119:105"]
    assert refs("Luke 1423") == ["Luke 14:23"]
    assert refs("Mark 16 15") == ["Mark 16:15"]


def test_ambiguous_run_together_digits_are_not_guessed():
    assert refs("Hebrews 1131") == []         # 11:31 or 1:131? do not guess in front of a congregation


def test_a_reference_is_acted_on_even_if_the_recogniser_goes_quiet_without_a_final_result():
    """Seen on the iMac: 'John chapter 3 verse 16' was the last partial and no final ever came."""
    shown = []
    run(stream(("partial", 9.85, "please turn with me to John chapter 3"), ("partial", 10.75, "please turn with me to John chapter 3 verse 16"),
               ("partial", 14.14, "Call"), ("partial", 15.25, "Paul says in Romans eight")),
        show=lambda r: shown.append(r) or True, log=lambda s: None)
    assert shown == ["John 3:16"]


def test_a_new_sentence_can_repeat_a_reference_after_the_cooldown():
    shown = []
    run(stream(("partial", 1.0, "John three sixteen"), ("status", 3.0, "x"), ("partial", 40.0, "Back to John three sixteen"), ("status", 42.0, "x")),
        show=lambda r: shown.append(r) or True, detector=Detector(cooldown=30), log=lambda s: None)
    assert shown == ["John 3:16", "John 3:16"]


def test_a_number_the_recogniser_is_still_revising_is_not_shown():
    """Seen live: 'Romans 820' appeared first, then became 'Romans 828'. The wrong verse must never be shown."""
    shown = []
    run(stream(("partial", 15.25, "Paul says in Romans eight"), ("partial", 15.54, "Paul says in Romans 820"),
               ("status", 16.5, "tick"), ("partial", 16.7, "Paul says in Romans 828"), ("partial", 17.0, "Paul says in Romans 828 that all"),
               ("partial", 18.0, "Paul says in Romans 828 that all things work")),
        show=lambda r: shown.append(r) or True, log=lambda s: None)
    assert shown == ["Romans 8:28"]


def test_a_reference_at_the_very_end_of_speech_is_shown_after_a_pause():
    shown = []
    run(stream(("partial", 10.0, "turn to John 316"), ("status", 11.0, "tick"), ("status", 12.0, "tick"), ("status", 12.5, "tick")),
        show=lambda r: shown.append(r) or True, log=lambda s: None)
    assert shown == ["John 3:16"]


def test_what_whisper_writes_is_understood():
    """Captured from whisper small.en/base.en on the iMac: dots for colons, hyphens for chapter-verse, commas."""
    assert refs("Habakkuk 2.4 says the righteous shall live by faith") == ["Habakkuk 2:4"]
    assert refs("In 1 Corinthians 13.4, Paul tells us love is patient") == ["1 Corinthians 13:4"]
    assert refs("open to Isaiah 40-31, and Genesis 1-1") == ["Isaiah 40:31", "Genesis 1:1"]
    assert refs("Compare that with Ephesians 2.8-9 and Zephaniah 3.17") == ["Ephesians 2:8-9", "Zephaniah 3:17"]
    assert refs("then look at Romans 8, 28.") == ["Romans 8:28"]
    assert refs("Psalm 119.105 is a lamp to my feet") == ["Psalms 119:105"]
    assert refs("2 Timothy 3.16 and 17") == ["2 Timothy 3:16"]
    assert refs("Philippians 4 13 he says") == ["Philippians 4:13"]
    assert refs("it costs 3.5 percent and 12.99 dollars") == []


def test_a_sound_alike_number_right_after_book_and_chapter_is_a_verse_number():
    """Whisper wrote 'Habakkuk 2 for' and 'Corinthians 13 for' when the pastor said four."""
    assert refs("Look at 1 Corinthians 13 for then Psalm 23 1 through 3.") == ["1 Corinthians 13:4", "Psalms 23:1-3"]
    assert refs("Open your Bible to Habakkuk 2 for and 2nd Timothy 3 16") == ["Habakkuk 2:4", "2 Timothy 3:16"]


def test_ordinary_words_after_a_reference_are_left_alone():
    assert refs("John 3 for God so loved the world") == []          # not John 3:4
    assert refs("we read John 3 and then we pray for us") == []
    assert refs("Romans 8 to the church in Rome") == []


def test_whisper_dash_after_a_book_is_chapter_and_verse():
    assert refs("Open your Bible to Habakkuk 2-4, and then look at Jude 24.") == ["Habakkuk 2:4", "Jude 1:24"]
    assert refs("Romans 8-28") == ["Romans 8:28"]
    assert refs("John 3-16") == ["John 3:16"]
    assert refs("Psalm 23 1-3") == ["Psalms 23:1-3"]            # a verse range after a chapter stays a range
    assert refs("Ephesians 2:8-9") == ["Ephesians 2:8-9"]


def test_a_reference_split_by_a_pause_is_read_whole():
    """Seen live: Whisper ended one sentence at 'John 3.' and the next began with 'verse 16'."""
    shown = []
    run(stream(("partial", 17.0, "Good evening. Please turn with me to John 3."), ("final", 18.6, "Good evening. Please turn with me to John 3."),
               ("partial", 19.4, "verse 16"), ("final", 20.0, "verse 16."), ("status", 24.0, "tick")),
        show=lambda r: shown.append(r) or True, log=lambda s: None)
    assert shown == ["John 3:16"]


def test_psalms_is_looked_up_as_psalm():
    from versevision_stt.listen_cli import _lookup_text
    assert _lookup_text("Psalms 23:1-3") == "Psalm 23:1-3"
    assert _lookup_text("John 3:16") == "John 3:16"


def test_listen_defaults_are_dante_displayed_thirty_seconds_into_verses():
    import inspect
    from versevision_stt.listen_cli import listen_command
    p = inspect.signature(listen_command).parameters
    assert p["device"].default == "Dante" and p["hold"].default == 30.0 and p["presentation"].default == "" and p["add"].default is False and p["preload"].default == 6 and p["fast"].default is True
    assert p["dry_run"].default is False and p["follow"].default is True and p["content"].default is True


def test_a_named_range_is_expanded_to_the_verses_a_lookup_produces():
    from versevision_stt.listen_cli import _range_text, range_verses
    from versevision_stt.scripture import ScriptureIndex, Verse
    idx = ScriptureIndex({"KJV": [Verse("PSA", "Psalms", 23, n, f"verse {n} text of the psalm here today") for n in range(1, 7)]
                          + [Verse("GEN", "Genesis", 1, 31, "x y z a b c d e"), Verse("GEN", "Genesis", 2, 1, "x y z a b c d e"), Verse("GEN", "Genesis", 2, 2, "x y z a b c d e")]})
    assert range_verses(idx, "PSA", 23, 1, (23, 3)) == [(23, 1), (23, 2), (23, 3)]
    assert range_verses(idx, "PSA", 23, 4, None) == [(23, 4)]
    assert range_verses(idx, "GEN", 1, 31, (2, 2)) == [(1, 31), (2, 1), (2, 2)]
    assert _range_text("Psalms", 23, 1, (23, 3)) == "Psalms 23:1-3" and _range_text("Genesis", 1, 31, (2, 2)) == "Genesis 1:31-2:2"
    assert _range_text("John", 3, 16, None) == "John 3:16"


def test_stt_uses_only_its_own_folders_and_never_the_importers(tmp_path, monkeypatch):
    from versevision_stt import stt_paths
    monkeypatch.delenv("VERSEVISION_STT_HOME", raising=False)
    p = stt_paths.paths()
    assert p.home.name == "VerseVision-STT" and "VerseVision-tools" not in str(p.home)
    for sub in (p.home, p.data, p.logs):
        assert "versevision-stt" in str(sub).lower() or sub.name == "VerseVision-STT"
    old = stt_paths.legacy()
    assert str(old.tools).endswith("VerseVision-tools") and old.tools != p.home and old.scripture != p.scripture and old.logs != p.logs / "listen"


def test_environment_overrides_move_every_folder(tmp_path, monkeypatch):
    from versevision_stt import stt_paths
    monkeypatch.setenv("VERSEVISION_STT_HOME", str(tmp_path / "h")); monkeypatch.setenv("VERSEVISION_STT_DATA", str(tmp_path / "d")); monkeypatch.setenv("VERSEVISION_STT_LOGS", str(tmp_path / "l"))
    p = stt_paths.paths()
    assert p.app_binary == tmp_path / "h" / "VerseVision Listen.app" / "Contents" / "MacOS" / "vvlisten" and p.scripture == tmp_path / "d" / "scripture"
    assert p.whisper_server == tmp_path / "h" / "whisper" / "whisper.cpp" / "build" / "bin" / "whisper-server" and p.logs == tmp_path / "l"


def test_migration_copies_the_old_whisper_and_texts_and_leaves_the_originals(tmp_path, monkeypatch):
    from versevision_stt import install_cli, stt_paths
    old_tools = tmp_path / "VerseVision-tools"; (old_tools / "whisper" / "whisper.cpp" / "build2" / "bin").mkdir(parents=True)
    (old_tools / "whisper" / "whisper.cpp" / "build2" / "bin" / "whisper-server").write_text("bin")
    monkeypatch.setattr("versevision_stt.install_cli._build_is_safe", lambda d: d.name == "build2")
    old_scr = tmp_path / "olddata" / "scripture"; old_scr.mkdir(parents=True); (old_scr / "KJV.json").write_text("{}")
    monkeypatch.setattr(stt_paths, "legacy", lambda: stt_paths.LegacyPaths(old_tools, old_scr, tmp_path / "oldlogs"))
    monkeypatch.setattr(install_cli, "legacy", stt_paths.legacy)
    monkeypatch.setenv("VERSEVISION_STT_HOME", str(tmp_path / "new")); monkeypatch.setenv("VERSEVISION_STT_DATA", str(tmp_path / "newdata"))
    p = stt_paths.paths()
    done = install_cli.migrate_from_importer(p, lambda m: None)
    assert set(done) == {"whisper", "bible texts"}
    assert p.whisper_server.exists() and (p.scripture / "KJV.json").exists()
    assert (old_tools / "whisper" / "whisper.cpp" / "build2" / "bin" / "whisper-server").exists() and (old_scr / "KJV.json").exists()


def test_uninstall_never_touches_the_importers_folders(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from versevision_stt.cli import app
    importer_tools = tmp_path / "VerseVision-tools"; importer_tools.mkdir(); (importer_tools / "vvdialog").write_text("importer helper")
    monkeypatch.setenv("VERSEVISION_STT_HOME", str(tmp_path / "VerseVision-STT")); monkeypatch.setenv("VERSEVISION_STT_DATA", str(tmp_path / "d")); monkeypatch.setenv("VERSEVISION_STT_LOGS", str(tmp_path / "l"))
    home = tmp_path / "VerseVision-STT"; (home / "VerseVision Listen.app").mkdir(parents=True); (home / "vvadd").write_text("x")
    result = CliRunner().invoke(app, ["uninstall", "--purge"])
    assert result.exit_code == 0 and not home.exists()
    assert (importer_tools / "vvdialog").read_text() == "importer helper"


def test_the_command_has_listen_and_the_install_commands():
    from typer.testing import CliRunner
    from versevision_stt.cli import app
    out = CliRunner().invoke(app, ["--help"]).output
    for word in ("listen", "install", "update", "doctor", "uninstall"):
        assert word in out


def test_migration_prefers_the_tuned_build_and_refuses_an_unsafe_one(tmp_path, monkeypatch):
    from versevision_stt import install_cli, stt_paths
    old_tools = tmp_path / "VerseVision-tools"
    for variant in ("build", "build2"):
        d = old_tools / "whisper" / "whisper.cpp" / variant / "bin"; d.mkdir(parents=True); (d / "whisper-server").write_text(variant)
    monkeypatch.setattr(stt_paths, "legacy", lambda: stt_paths.LegacyPaths(old_tools, tmp_path / "nodata", tmp_path / "nologs"))
    monkeypatch.setattr(install_cli, "legacy", stt_paths.legacy)
    monkeypatch.setenv("VERSEVISION_STT_HOME", str(tmp_path / "new")); monkeypatch.setenv("VERSEVISION_STT_DATA", str(tmp_path / "nd"))
    monkeypatch.setattr(install_cli, "_build_is_safe", lambda d: d.name == "build2")
    install_cli.migrate_from_importer(stt_paths.paths(), lambda m: None)
    assert (tmp_path / "new" / "whisper" / "whisper.cpp" / "build" / "bin" / "whisper-server").read_text() == "build2"
    monkeypatch.setattr(install_cli, "_build_is_safe", lambda d: False)
    import shutil; shutil.rmtree(tmp_path / "new")
    assert install_cli.migrate_from_importer(stt_paths.paths(), lambda m: None) == []
