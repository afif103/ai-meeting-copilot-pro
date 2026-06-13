"""Fail-closed tests for memory_review.json handling, plus transcript/
summary byte-for-byte integrity across the whole review lifecycle."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from _util import fake_summary, temp_env  # noqa: E402
from backend import memory_review, profile_store, session_store  # noqa: E402

UPD = [
    {"category": "decision", "text": "First decision", "reason": "a", "confidence": "high"},
    {"category": "preference", "text": "Second pref", "reason": "b", "confidence": "low"},
]


def _session_with(profile_id, updates):
    m = session_store.create_session("Transcript body here.",
                                     mode_id="meeting_discussion")
    session_store.save_summary(m["session_id"], fake_summary(updates), profile_id)
    return m["session_id"]


def _session(profile_id):
    return _session_with(profile_id, UPD)


def _summary_path(sid, profile_id):
    return session_store.session_review_path(sid, profile_id).parent / "summary.json"


# ---------- corrupt / missing summary must never erase review state ----------

def test_invalid_summary_json_preserves_review_state():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        props = memory_review.build_proposals(sid, p["id"])  # creates review
        memory_review.reject_proposal(sid, props[0]["proposal_id"], p["id"])
        rpath = session_store.session_review_path(sid, p["id"])
        before = rpath.read_bytes()
        _summary_path(sid, p["id"]).write_text("{ not valid json",
                                               encoding="utf-8")
        with pytest.raises(ValueError):
            memory_review.build_proposals(sid, p["id"])
        assert rpath.read_bytes() == before


def test_summary_read_failure_preserves_review_state():
    from pathlib import Path
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        memory_review.build_proposals(sid, p["id"])
        rpath = session_store.session_review_path(sid, p["id"])
        before = rpath.read_bytes()
        spath = _summary_path(sid, p["id"])
        real_read = Path.read_text

        def boom(self, *a, **k):
            if self == spath:
                raise OSError("summary read fails")
            return real_read(self, *a, **k)

        Path.read_text = boom
        try:
            with pytest.raises(OSError):
                memory_review.build_proposals(sid, p["id"])
        finally:
            Path.read_text = real_read
        assert rpath.read_bytes() == before


def test_complete_session_missing_summary_fails_closed():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])  # save_summary marks status complete
        memory_review.build_proposals(sid, p["id"])
        rpath = session_store.session_review_path(sid, p["id"])
        before = rpath.read_bytes()
        _summary_path(sid, p["id"]).unlink()
        with pytest.raises(ValueError):
            memory_review.build_proposals(sid, p["id"])
        assert rpath.read_bytes() == before


def _bad_summary(updates_value):
    return {"schema_version": 1, "title": "t", "overview": "o",
            "key_points": [], "decisions": [], "action_items": [],
            "open_questions": [], "suggested_memory_updates": updates_value}


def test_malformed_suggested_updates_list_fails_closed():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        memory_review.build_proposals(sid, p["id"])
        rpath = session_store.session_review_path(sid, p["id"])
        before = rpath.read_bytes()
        _summary_path(sid, p["id"]).write_text(
            json.dumps(_bad_summary("not a list")), encoding="utf-8")
        with pytest.raises(ValueError):
            memory_review.build_proposals(sid, p["id"])
        assert rpath.read_bytes() == before


def test_malformed_suggestion_entry_fails_closed():
    for bad in ([123], [{"category": "decision"}], [{"text": "   "}]):
        with temp_env():
            p = profile_store.create_profile("R")
            sid = _session(p["id"])
            memory_review.build_proposals(sid, p["id"])
            rpath = session_store.session_review_path(sid, p["id"])
            before = rpath.read_bytes()
            _summary_path(sid, p["id"]).write_text(
                json.dumps(_bad_summary(bad)), encoding="utf-8")
            with pytest.raises(ValueError):
                memory_review.build_proposals(sid, p["id"])
            assert rpath.read_bytes() == before


def test_valid_empty_suggestions_zero_proposals_not_reviewed():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session_with(p["id"], [])  # valid summary, no suggestions
        assert memory_review.build_proposals(sid, p["id"]) == []
        meta = session_store.get_session(sid, p["id"])["metadata"]
        assert meta["memory_status"] == "not_reviewed"


def test_pending_session_without_summary_builds_nothing():
    with temp_env():
        p = profile_store.create_profile("R")
        m = session_store.create_session("t.", mode_id="meeting_discussion")
        # no summary saved -> status stays 'pending', no review file
        assert memory_review.build_proposals(m["session_id"], p["id"]) == []
        rpath = session_store.session_review_path(m["session_id"], p["id"])
        assert not rpath.exists()  # nothing persisted, nothing to erase


# ---------- strict saved-summary validation (no coercion / defaults) ----------

def _valid_sugg(**overrides):
    s = {"category": "decision", "text": "Ship it", "reason": "agreed",
         "confidence": "high"}
    s.update(overrides)
    return s


def _full_summary(**overrides):
    s = {"schema_version": 1, "title": "t", "overview": "o", "key_points": [],
         "decisions": [], "action_items": [], "open_questions": [],
         "suggested_memory_updates": [_valid_sugg()]}
    s.update(overrides)
    return s


def _summary_failclosed(summary_dict):
    """Create a session, build + reject a proposal, overwrite the summary
    with summary_dict, then assert build_proposals fails closed and the
    review state (incl. the prior rejection) is preserved byte-for-byte."""
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        props = memory_review.build_proposals(sid, p["id"])
        rejected_id = props[0]["proposal_id"]
        memory_review.reject_proposal(sid, rejected_id, p["id"])
        rpath = session_store.session_review_path(sid, p["id"])
        before = rpath.read_bytes()
        _summary_path(sid, p["id"]).write_text(json.dumps(summary_dict),
                                               encoding="utf-8")
        with pytest.raises(ValueError):
            memory_review.build_proposals(sid, p["id"])
        assert rpath.read_bytes() == before  # review state preserved
        # the prior rejection is still on disk
        saved = json.loads(before.decode("utf-8"))
        by_id = {x["proposal_id"]: x for x in saved["proposals"]}
        assert by_id[rejected_id]["decision"] == "rejected"


def test_missing_summary_schema_version_fails_closed():
    s = _full_summary()
    del s["schema_version"]
    _summary_failclosed(s)


def test_unsupported_summary_schema_version_fails_closed():
    _summary_failclosed(_full_summary(schema_version=2))


def test_missing_suggested_updates_key_fails_closed():
    s = _full_summary()
    del s["suggested_memory_updates"]
    _summary_failclosed(s)


def test_each_missing_suggestion_field_fails_closed():
    for field in ("category", "text", "reason", "confidence"):
        sugg = _valid_sugg()
        del sugg[field]
        _summary_failclosed(_full_summary(suggested_memory_updates=[sugg]))


def test_non_string_suggestion_fields_fail_closed():
    for field, bad in (("category", 1), ("text", 2), ("reason", 3),
                       ("confidence", 4)):
        _summary_failclosed(
            _full_summary(suggested_memory_updates=[_valid_sugg(**{field: bad})]))


def test_invalid_category_fails_closed():
    _summary_failclosed(
        _full_summary(suggested_memory_updates=[_valid_sugg(category="bogus")]))


def test_invalid_confidence_fails_closed():
    _summary_failclosed(
        _full_summary(suggested_memory_updates=[_valid_sugg(confidence="maybe")]))


def test_empty_reason_is_allowed():
    # reason may be an empty string; a fully valid summary still builds
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session_with(
            p["id"], [_valid_sugg(reason="")])
        props = memory_review.build_proposals(sid, p["id"])
        assert len(props) == 1
        assert props[0]["reason"] == ""


# ---------- review-state fail-closed ----------

def test_invalid_json_fails_closed_and_is_byte_identical():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        memory_review.build_proposals(sid, p["id"])  # creates the file
        path = session_store.session_review_path(sid, p["id"])
        path.write_text("{ this is not valid json ", encoding="utf-8")
        before = path.read_bytes()
        with pytest.raises(ValueError):
            memory_review.build_proposals(sid, p["id"])
        assert path.read_bytes() == before


def _write_and_expect_failclosed(envelope_fn):
    """envelope_fn(sid) -> full top-level dict to write; assert
    build_proposals raises and the file is byte-identical."""
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        memory_review.build_proposals(sid, p["id"])
        path = session_store.session_review_path(sid, p["id"])
        path.write_text(json.dumps(envelope_fn(sid)), encoding="utf-8")
        before = path.read_bytes()
        with pytest.raises(ValueError):
            memory_review.build_proposals(sid, p["id"])
        assert path.read_bytes() == before


def test_unexpected_shape_fails_closed():
    # proposals not a list (valid envelope otherwise)
    _write_and_expect_failclosed(
        lambda sid: {"schema_version": 1, "session_id": sid,
                     "proposals": "not a list"})


def test_top_level_not_object_fails_closed():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        memory_review.build_proposals(sid, p["id"])
        path = session_store.session_review_path(sid, p["id"])
        path.write_text('["a", "list", "not", "an", "object"]', encoding="utf-8")
        before = path.read_bytes()
        with pytest.raises(ValueError):
            memory_review.build_proposals(sid, p["id"])
        assert path.read_bytes() == before


def test_wrong_schema_version_fails_closed():
    _write_and_expect_failclosed(
        lambda sid: {"schema_version": 999, "session_id": sid, "proposals": []})
    _write_and_expect_failclosed(
        lambda sid: {"session_id": sid, "proposals": []})  # missing


def test_wrong_or_missing_session_id_fails_closed():
    _write_and_expect_failclosed(
        lambda sid: {"schema_version": 1, "session_id": "20990101-000000-ffffff",
                     "proposals": []})
    _write_and_expect_failclosed(
        lambda sid: {"schema_version": 1, "session_id": 123, "proposals": []})
    _write_and_expect_failclosed(
        lambda sid: {"schema_version": 1, "proposals": []})  # missing


def test_inconsistent_decision_timestamp_fails_closed():
    valid_ts = "2026-06-13T00:00:00+00:00"

    def entry(sid, **ov):
        e = {"proposal_id": "p001-aaaaaaaa", "decision": "pending",
             "edited_text": "t", "applied_at_utc": None}
        e.update(ov)
        return {"schema_version": 1, "session_id": sid, "proposals": [e]}

    # approved but no timestamp
    _write_and_expect_failclosed(lambda sid: entry(sid, decision="approved"))
    # pending with a timestamp
    _write_and_expect_failclosed(
        lambda sid: entry(sid, decision="pending", applied_at_utc=valid_ts))
    # rejected with a timestamp
    _write_and_expect_failclosed(
        lambda sid: entry(sid, decision="rejected", applied_at_utc=valid_ts))


def test_read_failure_fails_closed_and_is_byte_identical():
    from pathlib import Path
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        memory_review.build_proposals(sid, p["id"])
        path = session_store.session_review_path(sid, p["id"])
        before = path.read_bytes()
        real_read = Path.read_text

        def boom(self, *a, **k):
            if self == path:
                raise OSError("simulated read failure")
            return real_read(self, *a, **k)

        Path.read_text = boom
        try:
            with pytest.raises(OSError):
                memory_review.build_proposals(sid, p["id"])
        finally:
            Path.read_text = real_read
        assert path.read_bytes() == before


def test_replace_failure_preserves_previous_state_and_cleans_temp():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        memory_review.build_proposals(sid, p["id"])  # valid file exists
        path = session_store.session_review_path(sid, p["id"])
        before = path.read_bytes()
        real_replace = os.replace

        def boom(src, dst):
            raise OSError("simulated replace failure")

        os.replace = boom
        try:
            with pytest.raises(OSError):
                # any state-changing op triggers _save -> replace
                memory_review.reject_proposal(
                    sid, memory_review.build_proposals(sid, p["id"])[0]["proposal_id"],
                    p["id"])
        finally:
            os.replace = real_replace
        assert path.read_bytes() == before              # previous state intact
        assert not list(path.parent.glob("*.json.tmp"))  # no temp leftover


def test_valid_state_restores_decisions_and_edits():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        props = memory_review.build_proposals(sid, p["id"])
        target = props[0]["proposal_id"]
        memory_review.set_edited_text(sid, target, "edited text", p["id"])
        memory_review.reject_proposal(sid, props[1]["proposal_id"], p["id"])
        # reload from disk
        again = {x["proposal_id"]: x for x in memory_review.build_proposals(sid, p["id"])}
        assert again[target]["edited_text"] == "edited text"
        assert again[props[1]["proposal_id"]]["decision"] == "rejected"


def test_approval_idempotent_after_review_save_failure():
    # If the permanent append succeeded but saving review state failed, a
    # retry must NOT append the memory a second time (marker recovery).
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        sid = _session(p["id"])
        target = memory_review.build_proposals(sid, p["id"])[0]["proposal_id"]
        mem = profile_store.get_profile_memory_dir(p["id"])

        # Fail the review-state save ONLY after the permanent append has
        # landed (decisions.md already holds the text). approve_proposal
        # saves review state twice - once inside build_proposals (before
        # the append) and once after; this targets the post-append save.
        real_replace = os.replace
        calls = {"n": 0}
        dec_path = mem / "decisions.md"

        def flaky(src, dst):
            if str(dst).endswith("memory_review.json"):
                if dec_path.exists() and "First decision" in dec_path.read_text(
                        encoding="utf-8"):
                    calls["n"] += 1
                    raise OSError("simulated review-save failure")
            return real_replace(src, dst)

        os.replace = flaky
        try:
            with pytest.raises(OSError):
                memory_review.approve_proposal(sid, target, p["id"])
        finally:
            os.replace = real_replace

        decisions = (mem / "decisions.md").read_text(encoding="utf-8")
        assert decisions.count("First decision") == 1   # appended once
        assert calls["n"] >= 1                            # review save did fail

        # Retry now succeeds and must NOT double-append (marker idempotency).
        memory_review.approve_proposal(sid, target, p["id"])
        decisions = (mem / "decisions.md").read_text(encoding="utf-8")
        assert decisions.count("First decision") == 1


# ---------- malformed proposal entries fail closed ----------

def _valid_entry(pid, **overrides):
    """A complete, schema-valid saved proposal entry; override one field
    to target a specific defect."""
    e = {"proposal_id": pid, "decision": "pending",
         "edited_text": "some text", "applied_at_utc": None}
    e.update(overrides)
    return e


def _expect_failclosed_with_proposals(proposals_value):
    """Write a review file whose 'proposals' is the given value, then
    assert build_proposals raises and the file is byte-identical."""
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        valid_pid = memory_review.build_proposals(sid, p["id"])[0]["proposal_id"]
        path = session_store.session_review_path(sid, p["id"])
        path.write_text(json.dumps({
            "schema_version": 1, "session_id": sid,
            "proposals": proposals_value(valid_pid),
        }), encoding="utf-8")
        before = path.read_bytes()
        with pytest.raises(ValueError):
            memory_review.build_proposals(sid, p["id"])
        assert path.read_bytes() == before


def _expect_load_ok_with_proposals(proposals_value):
    """Write a review file and assert build_proposals loads it without
    raising; returns the rebuilt {proposal_id: proposal} for assertions."""
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(p["id"])
        valid_pid = memory_review.build_proposals(sid, p["id"])[0]["proposal_id"]
        path = session_store.session_review_path(sid, p["id"])
        path.write_text(json.dumps({
            "schema_version": 1, "session_id": sid,
            "proposals": proposals_value(valid_pid),
        }), encoding="utf-8")
        rebuilt = {x["proposal_id"]: x
                   for x in memory_review.build_proposals(sid, p["id"])}
        return valid_pid, rebuilt


def test_non_object_proposal_entry_fails_closed():
    _expect_failclosed_with_proposals(lambda pid: ["a string entry"])
    _expect_failclosed_with_proposals(lambda pid: [123])
    _expect_failclosed_with_proposals(lambda pid: [None])


def test_invalid_proposal_id_fails_closed():
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry("p1")])      # old format
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry(pid, proposal_id=999)])


def test_duplicate_proposal_ids_fail_closed():
    _expect_failclosed_with_proposals(
        lambda pid: [_valid_entry(pid), _valid_entry(pid, decision="approved",
                                                     applied_at_utc="2026-01-01T00:00:00+00:00")])


def test_invalid_decision_fails_closed():
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry(pid, decision="maybe")])
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry(pid, decision=1)])


def test_malformed_edited_text_fails_closed():
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry(pid, edited_text=123)])
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry(pid, edited_text=["a", "b"])])
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry(pid, edited_text=None)])


def test_malformed_applied_at_fails_closed():
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry(pid, applied_at_utc=999)])


def test_empty_string_applied_at_is_rejected():
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry(pid, applied_at_utc="")])
    _expect_failclosed_with_proposals(lambda pid: [_valid_entry(pid, applied_at_utc="   ")])


def test_each_missing_required_field_fails_closed():
    for field in ("proposal_id", "decision", "edited_text", "applied_at_utc"):
        def drop(pid, f=field):
            e = _valid_entry(pid)
            del e[f]
            return [e]
        _expect_failclosed_with_proposals(drop)


def test_nullable_applied_at_none_loads_correctly():
    pid, rebuilt = _expect_load_ok_with_proposals(
        lambda pid: [_valid_entry(pid, decision="pending", applied_at_utc=None)])
    assert rebuilt[pid]["decision"] == "pending"
    assert rebuilt[pid]["applied_at_utc"] is None


def test_valid_approved_proposal_with_timestamp_restores():
    ts = "2026-06-13T00:00:00+00:00"
    pid, rebuilt = _expect_load_ok_with_proposals(
        lambda pid: [_valid_entry(pid, decision="approved",
                                  edited_text="my approved edit",
                                  applied_at_utc=ts)])
    assert rebuilt[pid]["decision"] == "approved"
    assert rebuilt[pid]["applied_at_utc"] == ts
    assert rebuilt[pid]["edited_text"] == "my approved edit"


# ---------- transcript / summary integrity across the lifecycle ----------

def test_transcript_and_summary_unchanged_by_review_lifecycle():
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        sid = _session(p["id"])
        d = profile_store.get_profile_memory_dir(p["id"]).parent / "sessions" / sid
        t_before = (d / "transcript.txt").read_bytes()
        s_before = (d / "summary.json").read_bytes()

        props = memory_review.build_proposals(sid, p["id"])
        memory_review.set_edited_text(sid, props[0]["proposal_id"], "edit", p["id"])
        memory_review.reject_proposal(sid, props[1]["proposal_id"], p["id"])
        memory_review.approve_proposal(sid, props[0]["proposal_id"], p["id"])
        memory_review.reset_proposal(sid, props[1]["proposal_id"], p["id"])

        assert (d / "transcript.txt").read_bytes() == t_before
        assert (d / "summary.json").read_bytes() == s_before


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
