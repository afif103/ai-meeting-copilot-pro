"""Tests for the read-only approved-memory library (Packet 7C)."""

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from _util import temp_env  # noqa: E402
from backend import memory_library, memory_store, profile_store  # noqa: E402

SID1 = "20260613-120000-aaaaaa"
SID2 = "20260613-130000-bbbbbb"


def _profile(name="Owner"):
    p = profile_store.create_profile(name)
    profile_store.set_active_profile_id(p["id"])
    memory_store.ensure_memory_files(p["id"])
    return p["id"], profile_store.get_profile_memory_dir(p["id"])


def _apply(profile_id, text, target, sid, pid):
    assert memory_store.apply_approved_memory_update(
        text, target, sid, pid, profile_id) is True


def test_valid_entry_parsed_correctly():
    with temp_env():
        pid_, _ = _profile()
        _apply(pid_, "Ship v2 on Friday", "decisions.md", SID1, "p001-aaaaaaaa")
        res = memory_library.read_approved_memory(pid_)
        assert res["warnings"] == 0
        assert len(res["entries"]) == 1
        e = res["entries"][0]
        assert e["text"] == "Ship v2 on Friday"
        assert e["target_file"] == "decisions.md"
        assert e["category"] == "decision"
        assert e["session_id"] == SID1
        assert e["proposal_id"] == "p001-aaaaaaaa"
        assert e["date"]  # a date string was parsed


def test_multiple_entries_newest_first():
    with temp_env():
        pid_, _ = _profile()
        # appended in order p001, p002, p003 -> p003 is newest
        _apply(pid_, "first", "decisions.md", SID1, "p001-aaaaaaaa")
        _apply(pid_, "second", "decisions.md", SID1, "p002-aaaaaaaa")
        _apply(pid_, "third", "decisions.md", SID1, "p003-aaaaaaaa")
        entries = memory_library.read_approved_memory(pid_)["entries"]
        assert [e["text"] for e in entries] == ["third", "second", "first"]


def test_multiline_text_preserved():
    with temp_env():
        pid_, _ = _profile()
        _apply(pid_, "line one\nline two\nline three", "notes.md",
               SID1, "p001-aaaaaaaa")
        e = memory_library.read_approved_memory(pid_)["entries"][0]
        assert e["text"] == "line one\nline two\nline three"


def test_source_and_proposal_traceable():
    with temp_env():
        pid_, _ = _profile()
        _apply(pid_, "task X", "ongoing_tasks.md", SID2, "p007-deadbeef")
        e = memory_library.read_approved_memory(pid_)["entries"][0]
        assert e["session_id"] == SID2 and e["proposal_id"] == "p007-deadbeef"


def test_manual_base_content_not_an_entry():
    with temp_env():
        pid_, mem = _profile()
        # a hand-written file with a heading but NO machine marker
        (mem / "notes.md").write_text(
            "# Notes\n\n## Memory update - not a real one\nSome manual note.\n",
            encoding="utf-8")
        res = memory_library.read_approved_memory(pid_)
        assert res["entries"] == []
        assert res["warnings"] == 0  # no marker at all -> nothing to warn about


def test_missing_files_produce_empty_result_safely():
    with temp_env():
        p = profile_store.create_profile("Empty")
        profile_store.set_active_profile_id(p["id"])
        # do NOT ensure_memory_files -> the target files do not exist
        res = memory_library.read_approved_memory(p["id"])
        assert res["entries"] == [] and res["warnings"] == 0


def test_malformed_block_excluded_with_warning():
    with temp_env():
        pid_, mem = _profile()
        _apply(pid_, "good one", "decisions.md", SID1, "p001-aaaaaaaa")
        # append a marker with NO body (incomplete block)
        with open(mem / "decisions.md", "a", encoding="utf-8") as f:
            f.write(f"\n<!-- memory-update:{SID1}:p002-aaaaaaaa -->\n")
        res = memory_library.read_approved_memory(pid_)
        assert len(res["entries"]) == 1          # only the good one
        assert res["entries"][0]["text"] == "good one"
        assert res["warnings"] == 1              # the incomplete block


def test_body_not_matching_marker_is_excluded():
    with temp_env():
        pid_, mem = _profile()
        # marker says p001 but body Proposal says p999 -> must not attach
        block = (f"\n<!-- memory-update:{SID1}:p001-aaaaaaaa -->\n"
                 f"## Memory update — 2026-06-13\n\n"
                 f"- Source session: {SID1}\n"
                 f"- Proposal: p999-ffffffff\n"
                 f"- Text: mismatched\n")
        with open(mem / "notes.md", "a", encoding="utf-8") as f:
            f.write(block)
        res = memory_library.read_approved_memory(pid_)
        assert res["entries"] == [] and res["warnings"] == 1


def test_invalid_session_or_proposal_ids_rejected():
    with temp_env():
        pid_, mem = _profile()
        for marker in (f"<!-- memory-update:badsession:p001-aaaaaaaa -->",
                       f"<!-- memory-update:{SID1}:p1 -->"):
            block = (f"\n{marker}\n## Memory update - 2026-06-13\n\n"
                     f"- Source session: x\n- Proposal: y\n- Text: t\n")
            with open(mem / "notes.md", "a", encoding="utf-8") as f:
                f.write(block)
        res = memory_library.read_approved_memory(pid_)
        assert res["entries"] == [] and res["warnings"] == 2


def test_profile_a_cannot_read_profile_b():
    with temp_env():
        a = profile_store.create_profile("A")
        b = profile_store.create_profile("B")
        profile_store.set_active_profile_id(a["id"])
        memory_store.ensure_memory_files(a["id"])
        memory_store.ensure_memory_files(b["id"])
        _apply(a["id"], "A secret decision", "decisions.md", SID1, "p001-aaaaaaaa")
        _apply(b["id"], "B private note", "notes.md", SID2, "p001-bbbbbbbb")
        a_texts = [e["text"] for e in memory_library.read_approved_memory(a["id"])["entries"]]
        b_texts = [e["text"] for e in memory_library.read_approved_memory(b["id"])["entries"]]
        assert a_texts == ["A secret decision"]
        assert b_texts == ["B private note"]
        assert "A secret decision" not in b_texts
        assert "B private note" not in a_texts


def test_no_active_profile_fails_closed():
    with temp_env():
        # two profiles, no unambiguous active -> get_active_profile_id raises
        profile_store.create_profile("A")
        profile_store.create_profile("B")
        reg_path = profile_store.PROFILES_DIR / "profiles.json"
        import json
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["active"] = "ghost"
        reg_path.write_text(json.dumps(reg), encoding="utf-8")
        with pytest.raises(ValueError):
            memory_library.read_approved_memory()


def test_unknown_profile_rejected():
    with temp_env():
        profile_store.create_profile("A")
        with pytest.raises(ValueError):
            memory_library.read_approved_memory("../escape")
        with pytest.raises(ValueError):
            memory_library.read_approved_memory("no-such-profile")


def test_open_and_refresh_leave_files_byte_identical():
    with temp_env():
        pid_, mem = _profile()
        _apply(pid_, "d one", "decisions.md", SID1, "p001-aaaaaaaa")
        _apply(pid_, "t one", "ongoing_tasks.md", SID1, "p002-aaaaaaaa")
        _apply(pid_, "n one\nwith two lines", "notes.md", SID1, "p003-aaaaaaaa")
        before = {f.name: f.read_bytes() for f in mem.glob("*.md")}
        # read repeatedly (open + several refreshes)
        for _ in range(3):
            memory_library.read_approved_memory(pid_)
        after = {f.name: f.read_bytes() for f in mem.glob("*.md")}
        assert after == before


def test_review_approval_then_library_shows_it():
    # Integration: approving via the Packet 7B review flow surfaces in the
    # 7C library, and the review state is unchanged by reading.
    from backend import memory_review, session_store

    def fake_summary(updates):
        return {"schema_version": 1, "title": "T", "overview": "o",
                "key_points": [], "decisions": [], "action_items": [],
                "open_questions": [], "suggested_memory_updates": updates}

    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        m = session_store.create_session("transcript.", mode_id="meeting_discussion")
        sid = m["session_id"]
        session_store.save_summary(sid, fake_summary(
            [{"category": "decision", "text": "Launch in March",
              "reason": "agreed", "confidence": "high"}]), p["id"])
        prop = memory_review.build_proposals(sid, p["id"])[0]
        memory_review.approve_proposal(sid, prop["proposal_id"], p["id"])

        res = memory_library.read_approved_memory(p["id"])
        assert len(res["entries"]) == 1
        e = res["entries"][0]
        assert e["text"] == "Launch in March"
        assert e["session_id"] == sid
        assert e["proposal_id"] == prop["proposal_id"]
        # review state still reports it approved (reading did not disturb it)
        again = memory_review.build_proposals(sid, p["id"])[0]
        assert again["decision"] == "approved" and again["applied_at_utc"]


# ---------- helpers for crafted-block tests ----------

def _block(sid, pid, text="hello", date="2026-06-13",
           ts="2026-06-13T12:00:00Z"):
    """A well-formed Packet 7B block (with timestamp unless ts is None)."""
    lines = [f"<!-- memory-update:{sid}:{pid} -->",
             f"## Memory update — {date}", "",
             f"- Source session: {sid}",
             f"- Proposal: {pid}"]
    if ts is not None:
        lines.append(f"- Approved at UTC: {ts}")
    tparts = text.split("\n")
    lines.append("- Text: " + tparts[0])
    lines += ["  " + t for t in tparts[1:]]
    return "\n" + "\n".join(lines) + "\n"


def _read_notes(raw):
    """Write raw block(s) into a fresh profile's notes.md and read."""
    with temp_env():
        pid_, mem = _profile()
        (mem / "notes.md").write_text("# Notes" + raw, encoding="utf-8")
        return memory_library.read_approved_memory(pid_)


# ---------- Fix 1: unreadable / invalid-encoding files ----------

def test_invalid_utf8_file_does_not_crash():
    with temp_env():
        pid_, mem = _profile()
        _apply(pid_, "good decision", "decisions.md", SID1, "p001-aaaaaaaa")
        (mem / "notes.md").write_bytes(b"# Notes\n\xff\xfe bad \x80\x81 bytes\n")
        before = {f.name: f.read_bytes() for f in mem.glob("*.md")}
        res = memory_library.read_approved_memory(pid_)
        assert any(e["text"] == "good decision" for e in res["entries"])
        assert res["warnings"] >= 1                       # the unreadable file
        after = {f.name: f.read_bytes() for f in mem.glob("*.md")}
        assert after == before                            # nothing rewritten


# ---------- Fix 2: malformed marker / strict block parsing ----------

def test_marker_with_whitespace_warns():
    raw = f"\n<!-- memory-update:{SID1} p001-aaaaaaaa -->\n## Memory update — 2026-06-13\n\n- Source session: x\n- Proposal: y\n- Text: t\n"
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_marker_missing_closing_warns():
    raw = f"\n<!-- memory-update:{SID1}:p001-aaaaaaaa\n## Memory update — 2026-06-13\n\n- Source session: x\n- Text: t\n"
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_marker_too_many_parts_warns():
    raw = f"\n<!-- memory-update:{SID1}:p001-aaaaaaaa:extra -->\n## Memory update — 2026-06-13\n\n- Text: t\n"
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_invalid_calendar_date_warns():
    raw = _block(SID1, "p001-aaaaaaaa", date="2026-13-45")  # impossible date
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_duplicate_source_field_malformed():
    raw = (f"\n<!-- memory-update:{SID1}:p001-aaaaaaaa -->\n"
           f"## Memory update — 2026-06-13\n\n"
           f"- Source session: {SID1}\n- Source session: {SID1}\n"
           f"- Proposal: p001-aaaaaaaa\n- Text: t\n")
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_duplicate_proposal_field_malformed():
    raw = (f"\n<!-- memory-update:{SID1}:p001-aaaaaaaa -->\n"
           f"## Memory update — 2026-06-13\n\n"
           f"- Source session: {SID1}\n"
           f"- Proposal: p001-aaaaaaaa\n- Proposal: p001-aaaaaaaa\n- Text: t\n")
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_duplicate_text_field_malformed():
    raw = (f"\n<!-- memory-update:{SID1}:p001-aaaaaaaa -->\n"
           f"## Memory update — 2026-06-13\n\n"
           f"- Source session: {SID1}\n- Proposal: p001-aaaaaaaa\n"
           f"- Text: one\n- Text: two\n")
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_malformed_marker_after_valid_block_keeps_valid_entry():
    raw = _block(SID1, "p001-aaaaaaaa", "valid text") + \
        "\n<!-- memory-update:totally broken -->\n"
    res = _read_notes(raw)
    assert len(res["entries"]) == 1
    assert res["entries"][0]["text"] == "valid text"
    assert res["warnings"] == 1


def test_duplicate_machine_ids_excluded_and_warned():
    raw = _block(SID1, "p001-aaaaaaaa", "first") + \
        _block(SID1, "p001-aaaaaaaa", "second")
    res = _read_notes(raw)
    assert res["entries"] == []        # both ambiguous copies excluded
    assert res["warnings"] == 2


# ---------- Fix 3: exact approval timestamp & ordering ----------

def test_apply_writes_a_valid_microsecond_timestamp():
    import datetime as _dt
    with temp_env():
        pid_, _ = _profile()
        _apply(pid_, "x", "decisions.md", SID1, "p001-aaaaaaaa")
        e = memory_library.read_approved_memory(pid_)["entries"][0]
        assert e["approved_at_utc"] is not None
        # apply now writes microsecond precision
        _dt.datetime.strptime(e["approved_at_utc"], "%Y-%m-%dT%H:%M:%S.%fZ")


def test_same_day_ordered_by_exact_timestamp_over_file_order():
    with temp_env():
        pid_, mem = _profile()
        # decisions.md comes BEFORE notes.md in file order, but the note
        # was approved later -> it must sort first (timestamp beats file).
        (mem / "decisions.md").write_text(
            "# Decisions" + _block(SID1, "p001-aaaaaaaa", "early decision",
                                   ts="2026-06-13T09:00:00Z"),
            encoding="utf-8")
        (mem / "notes.md").write_text(
            "# Notes" + _block(SID2, "p001-bbbbbbbb", "late note",
                               ts="2026-06-13T15:00:00Z"),
            encoding="utf-8")
        entries = memory_library.read_approved_memory(pid_)["entries"]
        assert [e["text"] for e in entries] == ["late note", "early decision"]


def test_later_decision_appears_before_earlier_note():
    with temp_env():
        pid_, mem = _profile()
        (mem / "notes.md").write_text(
            "# Notes" + _block(SID1, "p001-aaaaaaaa", "early note",
                               ts="2026-06-13T08:00:00Z"),
            encoding="utf-8")
        (mem / "decisions.md").write_text(
            "# Decisions" + _block(SID2, "p001-bbbbbbbb", "late decision",
                                   ts="2026-06-13T20:00:00Z"),
            encoding="utf-8")
        entries = memory_library.read_approved_memory(pid_)["entries"]
        assert entries[0]["text"] == "late decision"


def test_timestamp_preserved_in_record():
    with temp_env():
        pid_, mem = _profile()
        (mem / "decisions.md").write_text(
            "# Decisions" + _block(SID1, "p001-aaaaaaaa", "d",
                                   ts="2026-06-13T11:22:33Z"),
            encoding="utf-8")
        e = memory_library.read_approved_memory(pid_)["entries"][0]
        assert e["approved_at_utc"] == "2026-06-13T11:22:33Z"


def test_malformed_timestamp_warns():
    raw = (f"\n<!-- memory-update:{SID1}:p001-aaaaaaaa -->\n"
           f"## Memory update — 2026-06-13\n\n"
           f"- Source session: {SID1}\n- Proposal: p001-aaaaaaaa\n"
           f"- Approved at UTC: not-a-real-timestamp\n- Text: t\n")
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_legacy_date_only_block_displays():
    with temp_env():
        pid_, mem = _profile()
        (mem / "decisions.md").write_text(
            "# Decisions" + _block(SID1, "p001-aaaaaaaa", "legacy entry",
                                   ts=None),  # no Approved-at line
            encoding="utf-8")
        res = memory_library.read_approved_memory(pid_)
        assert len(res["entries"]) == 1
        assert res["entries"][0]["text"] == "legacy entry"
        assert res["entries"][0]["approved_at_utc"] is None


# ---------- strict heading (exact line only) ----------

def _block_heading(heading_line):
    return (f"\n<!-- memory-update:{SID1}:p001-aaaaaaaa -->\n"
            f"{heading_line}\n\n"
            f"- Source session: {SID1}\n- Proposal: p001-aaaaaaaa\n"
            f"- Text: t\n")


def test_malformed_headings_rejected():
    for bad in (
        "## Memory update GARBAGE 2026-06-13",
        "## Memory update — 2026-06-13 trailing",
        "prefix ## Memory update — 2026-06-13",
        "## Memory update - 2026-06-13 extra",   # hyphen, not em-dash
        "## Memory update — 2026/06/13",          # wrong date separators
        "##Memory update — 2026-06-13",           # missing space after ##
    ):
        res = _read_notes(_block_heading(bad))
        assert res["entries"] == [], f"accepted bad heading: {bad!r}"
        assert res["warnings"] == 1, f"no warning for: {bad!r}"


def test_exact_heading_accepted():
    res = _read_notes(_block_heading("## Memory update — 2026-06-13"))
    assert len(res["entries"]) == 1 and res["warnings"] == 0


# ---------- timestamp date must match heading date ----------

def _block_dates(heading_date, ts):
    return (f"\n<!-- memory-update:{SID1}:p001-aaaaaaaa -->\n"
            f"## Memory update — {heading_date}\n\n"
            f"- Source session: {SID1}\n- Proposal: p001-aaaaaaaa\n"
            f"- Approved at UTC: {ts}\n- Text: t\n")


def test_matching_date_and_timestamp_accepted():
    res = _read_notes(_block_dates("2026-06-13", "2026-06-13T12:00:00.500000Z"))
    assert len(res["entries"]) == 1 and res["warnings"] == 0


def test_timestamp_previous_day_rejected():
    res = _read_notes(_block_dates("2026-06-13", "2026-06-12T23:59:59Z"))
    assert res["entries"] == [] and res["warnings"] == 1


def test_timestamp_next_day_rejected():
    res = _read_notes(_block_dates("2026-06-13", "2026-06-14T00:00:00Z"))
    assert res["entries"] == [] and res["warnings"] == 1


def test_timestamp_with_offset_rejected():
    # not UTC 'Z' -> rejected
    res = _read_notes(_block_dates("2026-06-13", "2026-06-13T12:00:00+02:00"))
    assert res["entries"] == [] and res["warnings"] == 1


# ---------- sub-second ordering via parsed datetimes ----------

def test_same_second_microsecond_ordering():
    with temp_env():
        pid_, mem = _profile()
        (mem / "decisions.md").write_text(
            "# Decisions"
            + _block(SID1, "p001-aaaaaaaa", "earlier micro",
                     ts="2026-06-13T12:00:00.000100Z")
            + _block(SID2, "p002-bbbbbbbb", "later micro",
                     ts="2026-06-13T12:00:00.000900Z"),
            encoding="utf-8")
        entries = memory_library.read_approved_memory(pid_)["entries"]
        assert [e["text"] for e in entries] == ["later micro", "earlier micro"]


def test_microsecond_newer_beats_file_order():
    with temp_env():
        pid_, mem = _profile()
        # OLDER in decisions.md (earlier file); NEWER in notes.md (later file)
        (mem / "decisions.md").write_text(
            "# Decisions" + _block(SID2, "p001-bbbbbbbb", "old decision",
                                   ts="2026-06-13T12:00:00.000001Z"),
            encoding="utf-8")
        (mem / "notes.md").write_text(
            "# Notes" + _block(SID1, "p001-aaaaaaaa", "new note",
                               ts="2026-06-13T12:00:00.999999Z"),
            encoding="utf-8")
        entries = memory_library.read_approved_memory(pid_)["entries"]
        assert entries[0]["text"] == "new note"  # timestamp beats file order


def test_microsecond_timestamp_visible_in_record():
    with temp_env():
        pid_, mem = _profile()
        (mem / "decisions.md").write_text(
            "# Decisions" + _block(SID1, "p001-aaaaaaaa", "d",
                                   ts="2026-06-13T11:22:33.456789Z"),
            encoding="utf-8")
        e = memory_library.read_approved_memory(pid_)["entries"][0]
        assert e["approved_at_utc"] == "2026-06-13T11:22:33.456789Z"


def test_second_only_legacy_timestamp_still_parses_and_sorts():
    with temp_env():
        pid_, mem = _profile()
        (mem / "decisions.md").write_text(
            "# Decisions"
            + _block(SID1, "p001-aaaaaaaa", "sec earlier",
                     ts="2026-06-13T12:00:00Z")
            + _block(SID2, "p002-bbbbbbbb", "micro later",
                     ts="2026-06-13T12:00:00.500000Z"),
            encoding="utf-8")
        entries = memory_library.read_approved_memory(pid_)["entries"]
        assert [e["text"] for e in entries] == ["micro later", "sec earlier"]


# ---------- Fix 1: symlink / path-escape isolation ----------

def _try_symlink(link, target):
    try:
        os.symlink(target, link)
        return True
    except (OSError, NotImplementedError, AttributeError):
        return False  # Windows without privilege / unsupported -> skip


def test_regular_file_inside_memory_loads():
    with temp_env():
        pid_, _ = _profile()
        _apply(pid_, "normal entry", "notes.md", SID1, "p001-aaaaaaaa")
        res = memory_library.read_approved_memory(pid_)
        assert any(e["text"] == "normal entry" for e in res["entries"])
        assert res["warnings"] == 0


def test_symlink_to_other_profile_not_exposed():
    with temp_env():
        a = profile_store.create_profile("A")
        b = profile_store.create_profile("B")
        memory_store.ensure_memory_files(a["id"])
        memory_store.ensure_memory_files(b["id"])
        _apply(b["id"], "B secret decision", "notes.md", SID1, "p001-aaaaaaaa")
        a_mem = profile_store.get_profile_memory_dir(a["id"])
        b_mem = profile_store.get_profile_memory_dir(b["id"])
        a_notes, b_notes = a_mem / "notes.md", b_mem / "notes.md"
        b_before = b_notes.read_bytes()
        a_notes.unlink()  # replace A's regular file with a link to B's
        if not _try_symlink(a_notes, b_notes):
            pytest.skip("symlinks not creatable here (runs on Linux CI)")
        res = memory_library.read_approved_memory(a["id"])
        assert all(e["text"] != "B secret decision" for e in res["entries"])
        assert res["warnings"] >= 1
        assert a_notes.is_symlink()           # link left intact (not removed)
        assert b_notes.read_bytes() == b_before  # B's file untouched


def test_symlink_outside_memory_dir_rejected():
    with temp_env():
        pid_, mem = _profile()
        notes = mem / "notes.md"
        outside = mem.parent.parent.parent / "outside_notes.md"  # under data/
        outside.write_text(
            "# Outside" + _block(SID1, "p001-aaaaaaaa", "outside entry"),
            encoding="utf-8")
        before = outside.read_bytes()
        notes.unlink()
        if not _try_symlink(notes, outside):
            pytest.skip("symlinks not creatable here (runs on Linux CI)")
        res = memory_library.read_approved_memory(pid_)
        assert all(e["text"] != "outside entry" for e in res["entries"])
        assert res["warnings"] >= 1
        assert outside.read_bytes() == before  # outside file untouched


def test_safe_regular_file_helper(monkeypatch):
    # platform-independent: a real regular file inside the dir is safe...
    with temp_env():
        pid_, mem = _profile()
        notes = mem / "notes.md"
        notes.write_text("# Notes\n", encoding="utf-8")
        mem_real = mem.resolve()
        assert memory_library._safe_regular_file(notes, mem_real) is True
        # ...but if it RESOLVES outside the dir it must be rejected.
        outside = mem_real.parent / "elsewhere.md"
        real_resolve = Path.resolve

        def fake(self, *a, **k):
            return outside if self == notes else real_resolve(self, *a, **k)

        monkeypatch.setattr(Path, "resolve", fake)
        assert memory_library._safe_regular_file(notes, mem_real) is False


def test_mocked_redirected_target_excluded_and_warned(monkeypatch):
    with temp_env():
        pid_, mem = _profile()
        _apply(pid_, "leak me", "notes.md", SID1, "p001-aaaaaaaa")
        notes = mem / "notes.md"
        before = notes.read_bytes()
        outside = mem.resolve().parent / "elsewhere.md"
        real_resolve = Path.resolve

        def fake(self, *a, **k):
            return outside if self == notes else real_resolve(self, *a, **k)

        monkeypatch.setattr(Path, "resolve", fake)
        res = memory_library.read_approved_memory(pid_)
        assert all(e["target_file"] != "notes.md" for e in res["entries"])
        assert res["warnings"] >= 1
        assert notes.read_bytes() == before  # never read-through, never mutated


# ---------- Fix 2: full physical marker-line validation ----------

GOOD_MARKER = f"<!-- memory-update:{SID1}:p001-aaaaaaaa -->"


def _marker_body(marker_line):
    """A block whose body is canonical; only the marker LINE varies."""
    return (f"\n{marker_line}\n"
            f"## Memory update — 2026-06-13\n\n"
            f"- Source session: {SID1}\n- Proposal: p001-aaaaaaaa\n"
            f"- Text: t\n")


def test_standalone_marker_accepted():
    res = _read_notes(_marker_body(GOOD_MARKER))
    assert len(res["entries"]) == 1 and res["warnings"] == 0


def test_marker_leading_spaces_rejected():
    res = _read_notes(_marker_body("   " + GOOD_MARKER))
    assert res["entries"] == [] and res["warnings"] == 1


def test_marker_leading_tab_rejected():
    res = _read_notes(_marker_body("\t" + GOOD_MARKER))
    assert res["entries"] == [] and res["warnings"] == 1


def test_marker_leading_text_rejected():
    res = _read_notes(_marker_body("prefix " + GOOD_MARKER))
    assert res["entries"] == [] and res["warnings"] == 1


def test_marker_trailing_text_rejected():
    res = _read_notes(_marker_body(GOOD_MARKER + " trailing"))
    assert res["entries"] == [] and res["warnings"] == 1


def test_inline_marker_does_not_absorb_preceding_valid_block():
    with temp_env():
        pid_, mem = _profile()
        valid = _block(SID1, "p001-aaaaaaaa", "valid one")
        bad = (f"   <!-- memory-update:{SID2}:p002-bbbbbbbb -->\n"
               f"## Memory update — 2026-06-13\n\n"
               f"- Source session: {SID2}\n- Proposal: p002-bbbbbbbb\n"
               f"- Text: should not attach\n")
        (mem / "notes.md").write_text(
            "# Notes" + valid + "\n" + bad, encoding="utf-8")
        res = memory_library.read_approved_memory(pid_)
        assert [e["text"] for e in res["entries"]] == ["valid one"]
        assert res["warnings"] == 1  # the indented marker, isolated


# ---------- Fix 3: malformed reserved lines reject the block ----------

def test_extra_malformed_heading_rejects_block():
    raw = (f"\n{GOOD_MARKER}\n"
           f"## Memory update — 2026-06-13\n"
           f"## Memory update GARBAGE\n\n"
           f"- Source session: {SID1}\n- Proposal: p001-aaaaaaaa\n- Text: t\n")
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_malformed_source_line_rejects_block():
    raw = (f"\n{GOOD_MARKER}\n## Memory update — 2026-06-13\n\n"
           f"- Source session:{SID1}\n"            # missing space after colon
           f"- Proposal: p001-aaaaaaaa\n- Text: t\n")
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_malformed_proposal_line_rejects_block():
    raw = (f"\n{GOOD_MARKER}\n## Memory update — 2026-06-13\n\n"
           f"- Source session: {SID1}\n"
           f"- Proposal:  p001-aaaaaaaa\n"          # double space
           f"- Text: t\n")
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_malformed_approved_at_line_rejects_block():
    raw = (f"\n{GOOD_MARKER}\n## Memory update — 2026-06-13\n\n"
           f"- Source session: {SID1}\n- Proposal: p001-aaaaaaaa\n"
           f"- Approved at UTC:\n"                  # no value
           f"- Text: t\n")
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_malformed_text_line_rejects_block():
    raw = (f"\n{GOOD_MARKER}\n## Memory update — 2026-06-13\n\n"
           f"- Source session: {SID1}\n- Proposal: p001-aaaaaaaa\n"
           f"- Text\n")                             # no colon
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


def test_extra_malformed_reserved_after_text_rejects_block():
    raw = (f"\n{GOOD_MARKER}\n## Memory update — 2026-06-13\n\n"
           f"- Source session: {SID1}\n- Proposal: p001-aaaaaaaa\n"
           f"- Text: valid text\n"
           f"- Proposal: garbage\n")                # trailing malformed field
    res = _read_notes(raw)
    assert res["entries"] == [] and res["warnings"] == 1


# ---------- Fix 4: canonical timestamp precision ----------

def test_noncanonical_fractional_timestamps_rejected():
    for frac in (".1", ".123", ".12345", ".1234567"):
        ts = "2026-06-13T12:00:00" + frac + "Z"
        res = _read_notes(_block_dates("2026-06-13", ts))
        assert res["entries"] == [], f"accepted {ts}"
        assert res["warnings"] == 1, f"no warning for {ts}"


def test_canonical_second_and_microsecond_timestamps_accepted():
    for ts in ("2026-06-13T12:00:00Z",
               "2026-06-13T12:00:00.000000Z",
               "2026-06-13T12:00:00.123456Z"):
        res = _read_notes(_block_dates("2026-06-13", ts))
        assert len(res["entries"]) == 1 and res["warnings"] == 0, ts


def test_non_utc_named_timestamp_rejected():
    # no trailing 'Z' -> not UTC canonical -> rejected
    res = _read_notes(_block_dates("2026-06-13", "2026-06-13T12:00:00"))
    assert res["entries"] == [] and res["warnings"] == 1


# ---------- Fix (v5): directory-chain isolation ----------

def _try_dir_symlink(link, target):
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError, AttributeError):
        return False  # Windows without privilege / unsupported -> skip


def _two_profiles_with_b_entry():
    a = profile_store.create_profile("A")
    b = profile_store.create_profile("B")
    memory_store.ensure_memory_files(a["id"])
    memory_store.ensure_memory_files(b["id"])
    _apply(b["id"], "B only fact", "notes.md", SID1, "p001-aaaaaaaa")
    return a, b


def test_valid_normal_memory_dir_loads():
    with temp_env():
        pid_, _ = _profile()
        _apply(pid_, "normal chain fact", "notes.md", SID1, "p001-aaaaaaaa")
        res = memory_library.read_approved_memory(pid_)
        assert any(e["text"] == "normal chain fact" for e in res["entries"])
        assert res["warnings"] == 0


def test_missing_memory_dir_is_safe_empty():
    with temp_env():
        a = profile_store.create_profile("A")
        a_mem = profile_store.get_profile_memory_dir(a["id"])
        shutil.rmtree(a_mem)  # remove the real (plain) memory directory
        res = memory_library.read_approved_memory(a["id"])
        assert res["entries"] == [] and res["warnings"] == 0


def test_memory_dir_symlinked_to_other_profile_not_exposed():
    with temp_env():
        a, b = _two_profiles_with_b_entry()
        a_mem = profile_store.get_profile_memory_dir(a["id"])
        b_mem = profile_store.get_profile_memory_dir(b["id"])
        b_before = {f.name: f.read_bytes() for f in b_mem.glob("*.md")}
        shutil.rmtree(a_mem)
        if not _try_dir_symlink(a_mem, b_mem):
            pytest.skip("dir symlinks not creatable here (runs on Linux CI)")
        res = memory_library.read_approved_memory(a["id"])
        assert res["entries"] == []          # B's entry NOT exposed under A
        assert res["warnings"] >= 1
        assert a_mem.is_symlink()            # link left intact (not removed)
        assert {f.name: f.read_bytes()
                for f in b_mem.glob("*.md")} == b_before  # B untouched


def test_profile_dir_symlinked_to_other_profile_rejected():
    with temp_env():
        a, b = _two_profiles_with_b_entry()
        root = profile_store.PROFILES_DIR
        a_dir, b_dir = root / a["id"], root / b["id"]
        b_mem = b_dir / "memory"
        b_before = {f.name: f.read_bytes() for f in b_mem.glob("*.md")}
        shutil.rmtree(a_dir)
        if not _try_dir_symlink(a_dir, b_dir):
            pytest.skip("dir symlinks not creatable here (runs on Linux CI)")
        res = memory_library.read_approved_memory(a["id"])
        assert res["entries"] == []
        assert res["warnings"] >= 1
        assert a_dir.is_symlink()
        assert {f.name: f.read_bytes()
                for f in b_mem.glob("*.md")} == b_before


def test_memory_dir_link_to_external_dir_rejected():
    with temp_env():
        pid_, a_mem = _profile()
        external = profile_store.PROFILES_DIR.parent / "external_mem"
        external.mkdir(parents=True, exist_ok=True)
        (external / "notes.md").write_text(
            "# X" + _block(SID1, "p001-aaaaaaaa", "external fact"),
            encoding="utf-8")
        ext_before = (external / "notes.md").read_bytes()
        shutil.rmtree(a_mem)
        if not _try_dir_symlink(a_mem, external):
            pytest.skip("dir symlinks not creatable here (runs on Linux CI)")
        res = memory_library.read_approved_memory(pid_)
        assert res["entries"] == []
        assert res["warnings"] >= 1
        assert (external / "notes.md").read_bytes() == ext_before  # untouched


def test_directory_symlink_loop_fails_closed():
    with temp_env():
        pid_, a_mem = _profile()
        shutil.rmtree(a_mem)
        if not _try_dir_symlink(a_mem, a_mem):  # self-referential loop
            pytest.skip("dir symlinks not creatable here (runs on Linux CI)")
        res = memory_library.read_approved_memory(pid_)  # must not crash
        assert res["entries"] == [] and res["warnings"] >= 1


def test_chain_resolve_runtime_error_fails_closed(monkeypatch):
    # platform-independent: a resolution loop raises RuntimeError -> closed
    with temp_env():
        pid_, a_mem = _profile()
        _apply(pid_, "A fact", "notes.md", SID1, "p001-aaaaaaaa")
        before = (a_mem / "notes.md").read_bytes()
        real_resolve = Path.resolve

        def boom(self, *a, **k):
            if self == a_mem:
                raise RuntimeError("Symlink loop")
            return real_resolve(self, *a, **k)

        monkeypatch.setattr(Path, "resolve", boom)
        res = memory_library.read_approved_memory(pid_)
        assert res["entries"] == [] and res["warnings"] == 1
        assert (a_mem / "notes.md").read_bytes() == before  # never read/mutated


def test_mocked_memory_dir_redirected_to_other_profile_rejected(monkeypatch):
    # platform-independent cross-profile redirection via mocked resolve()
    with temp_env():
        a, b = _two_profiles_with_b_entry()
        a_mem = profile_store.get_profile_memory_dir(a["id"])
        b_mem = profile_store.get_profile_memory_dir(b["id"])
        b_real = b_mem.resolve()
        real_resolve = Path.resolve

        def fake(self, *a, **k):
            return b_real if self == a_mem else real_resolve(self, *a, **k)

        monkeypatch.setattr(Path, "resolve", fake)
        res = memory_library.read_approved_memory(a["id"])
        assert res["entries"] == []          # resolves to B -> rejected
        assert res["warnings"] >= 1


# ---------- Fix (v6) #1: strict profile-id validation ----------

@pytest.mark.parametrize("bad", [
    "/etc/passwd",            # absolute POSIX
    "C:\\temp\\outside",      # Windows drive path
    "\\\\server\\share",      # UNC
    "../outside",             # traversal
    "a/b",                    # forward slash
    "a\\b",                   # backslash
    "a:b",                    # colon
    "-lead",                  # leading hyphen
    "trail-",                 # trailing hyphen
    "UPPER",                  # uppercase
    "a--b",                   # double hyphen (non-canonical separator)
    "a.b",                    # dot
    "..",                     # dot-dot only
    "a b",                    # space
])
def test_invalid_profile_ids_rejected(bad):
    with temp_env():
        _profile()  # a valid active profile also exists
        with pytest.raises(ValueError):
            memory_library.read_approved_memory(bad)


def test_non_string_profile_id_rejected():
    with temp_env():
        _profile()
        with pytest.raises(ValueError):
            memory_library.read_approved_memory(123)


def test_unregistered_id_rejected():
    # lexically valid but not in the registry -> rejected via membership
    with temp_env():
        _profile()  # some other valid profile exists
        with pytest.raises(ValueError):
            memory_library.read_approved_memory("ghost-profile")


def test_canonical_profile_id_accepted():
    with temp_env():
        pid_, _ = _profile()
        # the id created by the normal flow is canonical -> no raise
        memory_library.read_approved_memory(pid_)


def test_validate_profile_id_accepts_canonical_and_collision():
    # unit-level: includes collision-suffixed ids that EXCEED _MAX_ID_LEN
    for good in ("rami", "john-doe", "a1-b2-c3", "a" * 40,
                 "a" * 40 + "-2", "a" * 40 + "-3", "x" * 40 + "-10"):
        assert memory_library._validate_profile_id(good) == good


def test_validate_profile_id_rejects_noncanonical():
    for bad in ("/etc/passwd", "C:\\x\\y", "\\\\srv\\share", "../x", "a/b",
                "a\\b", "a:b", "-x", "x-", "Upper", "a--b", "a.b", "..",
                "a b", "", "a_b"):
        with pytest.raises(ValueError):
            memory_library._validate_profile_id(bad)
    for bad in (123, None, ["a"], b"bytes"):
        with pytest.raises(ValueError):
            memory_library._validate_profile_id(bad)


def test_long_collision_generated_profile_ids_load():
    # the normal creation flow generates "<base>-2"/"-3" ids longer than 40
    with temp_env():
        base = "a" * 40
        p1 = profile_store.create_profile(base)        # id == base (40)
        p2 = profile_store.create_profile(base + "b")  # slug collides -> -2
        p3 = profile_store.create_profile(base + "c")  # -> -3
        assert p1["id"] == base and len(p1["id"]) == 40
        assert p2["id"] == base + "-2" and len(p2["id"]) == 42
        assert p3["id"] == base + "-3"
        for p, fact in ((p1, "fact one"), (p2, "fact two"), (p3, "fact 3")):
            memory_store.ensure_memory_files(p["id"])
            _apply(p["id"], fact, "notes.md", SID1, "p001-aaaaaaaa")
            res = memory_library.read_approved_memory(p["id"])  # must not raise
            assert res["warnings"] == 0
            assert [e["text"] for e in res["entries"]] == [fact]


def test_corrupted_registry_absolute_id_fails_closed():
    with temp_env():
        profile_store.create_profile("Good")  # a normal profile exists
        # the external memory an attacker hopes to surface through A
        evil = profile_store.PROFILES_DIR.parent / "evil"
        (evil / "memory").mkdir(parents=True, exist_ok=True)
        ext = evil / "memory" / "notes.md"
        ext.write_text(
            "# X" + _block(SID1, "p001-aaaaaaaa", "evil external fact"),
            encoding="utf-8")
        ext_before = ext.read_bytes()
        # corrupt profiles.json: register an ABSOLUTE path id and make active
        bad_id = str(evil.resolve())
        reg_path = profile_store.PROFILES_DIR / "profiles.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["profiles"][bad_id] = {"display_name": "evil"}
        reg["active"] = bad_id
        reg_path.write_text(json.dumps(reg), encoding="utf-8")
        # fails closed BEFORE constructing/reading any external path
        with pytest.raises(ValueError):
            memory_library.read_approved_memory()        # active -> bad_id
        with pytest.raises(ValueError):
            memory_library.read_approved_memory(bad_id)  # explicit too
        assert ext.read_bytes() == ext_before            # external untouched


# ---------- Fix (v6) #2: hard-link rejection ----------

def _try_hardlink(link, target):
    try:
        os.link(target, link)
        return True
    except (OSError, NotImplementedError, AttributeError):
        return False  # filesystem doesn't support it here -> skip


def test_link_count_one_file_loads():
    with temp_env():
        pid_, _ = _profile()
        _apply(pid_, "single link fact", "notes.md", SID1, "p001-aaaaaaaa")
        res = memory_library.read_approved_memory(pid_)
        assert any(e["text"] == "single link fact" for e in res["entries"])
        assert res["warnings"] == 0


def test_hardlink_to_other_profile_not_exposed():
    with temp_env():
        a, b = _two_profiles_with_b_entry()
        a_mem = profile_store.get_profile_memory_dir(a["id"])
        b_mem = profile_store.get_profile_memory_dir(b["id"])
        a_notes, b_notes = a_mem / "notes.md", b_mem / "notes.md"
        b_before = b_notes.read_bytes()
        a_notes.unlink()
        if not _try_hardlink(a_notes, b_notes):
            pytest.skip("hard links unsupported here (runs on Linux CI)")
        res = memory_library.read_approved_memory(a["id"])
        assert all(e["text"] != "B only fact" for e in res["entries"])
        assert res["warnings"] >= 1
        assert a_notes.exists()                       # both names still present
        assert b_notes.read_bytes() == b_before       # shared content untouched


def test_hardlink_to_external_file_rejected():
    with temp_env():
        pid_, a_mem = _profile()
        external = profile_store.PROFILES_DIR.parent / "external_notes.md"
        external.write_text(
            "# X" + _block(SID1, "p001-aaaaaaaa", "external fact"),
            encoding="utf-8")
        ext_before = external.read_bytes()
        a_notes = a_mem / "notes.md"
        a_notes.unlink()
        if not _try_hardlink(a_notes, external):
            pytest.skip("hard links unsupported here (runs on Linux CI)")
        res = memory_library.read_approved_memory(pid_)
        assert all(e["text"] != "external fact" for e in res["entries"])
        assert res["warnings"] >= 1
        assert external.read_bytes() == ext_before     # external untouched


def test_other_files_display_when_one_hardlinked():
    with temp_env():
        a, b = _two_profiles_with_b_entry()
        a_mem = profile_store.get_profile_memory_dir(a["id"])
        b_mem = profile_store.get_profile_memory_dir(b["id"])
        _apply(a["id"], "A decision stays", "decisions.md", SID2, "p002-cccccccc")
        a_notes, b_notes = a_mem / "notes.md", b_mem / "notes.md"
        a_notes.unlink()
        if not _try_hardlink(a_notes, b_notes):
            pytest.skip("hard links unsupported here (runs on Linux CI)")
        texts = [e["text"]
                 for e in memory_library.read_approved_memory(a["id"])["entries"]]
        assert "A decision stays" in texts             # other A file still shows
        assert "B only fact" not in texts              # hard-linked target out


def test_mocked_hardlink_count_rejected(monkeypatch):
    # platform-independent: patch ONLY the link-count helper (NOT os.lstat,
    # which Path.resolve() needs intact on POSIX) so st_nlink > 1 rejects.
    with temp_env():
        pid_, mem = _profile()
        _apply(pid_, "leak me", "notes.md", SID1, "p001-aaaaaaaa")
        notes = mem / "notes.md"
        before = notes.read_bytes()
        real_count = memory_library._hard_link_count

        def fake(p):
            return 2 if str(p) == str(notes) else real_count(p)

        monkeypatch.setattr(memory_library, "_hard_link_count", fake)
        res = memory_library.read_approved_memory(pid_)
        assert all(e["text"] != "leak me" for e in res["entries"])
        assert all(e["target_file"] != "notes.md" for e in res["entries"])
        assert res["warnings"] >= 1
        assert notes.read_bytes() == before            # never read / mutated


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
