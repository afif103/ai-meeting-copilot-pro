"""Proposal-identity, review-state, and status tests for memory_review."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from _util import fake_summary, temp_env  # noqa: E402
from backend import memory_review, profile_store, session_store  # noqa: E402

DUP = [
    {"category": "decision", "text": "same text", "reason": "r", "confidence": "high"},
    {"category": "decision", "text": "same text", "reason": "r", "confidence": "high"},
]
TWO = [
    {"category": "decision", "text": "First decision", "reason": "a", "confidence": "high"},
    {"category": "preference", "text": "Second pref", "reason": "b", "confidence": "low"},
]


def _session(updates, profile_id):
    m = session_store.create_session("transcript.", mode_id="meeting_discussion")
    session_store.save_summary(m["session_id"], fake_summary(updates), profile_id)
    return m["session_id"]


def test_identical_suggestions_get_distinct_ids():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(DUP, p["id"])
        props = memory_review.build_proposals(sid, p["id"])
        ids = [x["proposal_id"] for x in props]
        assert len(ids) == 2 and len(set(ids)) == 2
        assert ids[0].startswith("p001-") and ids[1].startswith("p002-")


def test_ids_stable_and_state_restored_across_restart():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(TWO, p["id"])
        props = memory_review.build_proposals(sid, p["id"])
        target = props[0]["proposal_id"]
        memory_review.reject_proposal(sid, target, p["id"])
        # simulate restart: rebuild from disk
        again = memory_review.build_proposals(sid, p["id"])
        ids = [x["proposal_id"] for x in again]
        assert ids == [props[0]["proposal_id"], props[1]["proposal_id"]]
        by_id = {x["proposal_id"]: x for x in again}
        assert by_id[target]["decision"] == "rejected"


def test_reordered_summary_does_not_inherit_wrong_decision():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(TWO, p["id"])
        props = memory_review.build_proposals(sid, p["id"])
        memory_review.reject_proposal(sid, props[0]["proposal_id"], p["id"])
        # retry yields a reordered summary
        session_store.save_summary(sid, fake_summary(list(reversed(TWO))), p["id"])
        after = memory_review.build_proposals(sid, p["id"])
        top = after[0]
        assert top["original_text"] == "Second pref"
        assert top["decision"] == "pending"  # did not inherit the rejection


def test_unknown_proposal_id_rejected():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(TWO, p["id"])
        memory_review.build_proposals(sid, p["id"])
        with pytest.raises(ValueError):
            memory_review.reject_proposal(sid, "p999-deadbeef", p["id"])


def test_zero_proposals_is_not_reviewed():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session([], p["id"])
        assert memory_review.build_proposals(sid, p["id"]) == []
        meta = session_store.get_session(sid, p["id"])["metadata"]
        assert meta["memory_status"] == "not_reviewed"


def test_status_transitions():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(TWO, p["id"])
        props = memory_review.build_proposals(sid, p["id"])

        def status():
            return session_store.get_session(sid, p["id"])["metadata"]["memory_status"]

        assert status() == "not_reviewed"
        memory_review.approve_proposal(sid, props[0]["proposal_id"], p["id"])
        assert status() == "partially_reviewed"
        memory_review.reject_proposal(sid, props[1]["proposal_id"], p["id"])
        assert status() == "fully_reviewed"


def test_building_proposals_writes_no_memory():
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        sid = _session(TWO, p["id"])
        mem = profile_store.get_profile_memory_dir(p["id"])
        before = {f.name: f.read_bytes() for f in mem.glob("*.md")}
        memory_review.build_proposals(sid, p["id"])  # no auto-approve
        after = {f.name: f.read_bytes() for f in mem.glob("*.md")}
        assert before == after


def test_reject_writes_no_memory():
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        sid = _session(TWO, p["id"])
        props = memory_review.build_proposals(sid, p["id"])
        mem = profile_store.get_profile_memory_dir(p["id"])
        before = {f.name: f.read_bytes() for f in mem.glob("*.md")}
        memory_review.reject_proposal(sid, props[0]["proposal_id"], p["id"])
        after = {f.name: f.read_bytes() for f in mem.glob("*.md")}
        assert before == after


def test_unknown_memory_status_rejected():
    with temp_env():
        p = profile_store.create_profile("R")
        sid = _session(TWO, p["id"])
        with pytest.raises(ValueError):
            session_store.set_memory_status(sid, "bananas", p["id"])


def test_two_sessions_with_shared_proposal_id_keep_independent_edits():
    # Two sessions with identical suggestion content produce the SAME
    # proposal_id; editing/approving one must never use the other's text.
    # This is the data-layer guarantee behind per-window widget state.
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        sx = _session(DUP, p["id"])
        sy = _session(DUP, p["id"])
        px = memory_review.build_proposals(sx, p["id"])[0]["proposal_id"]
        py = memory_review.build_proposals(sy, p["id"])[0]["proposal_id"]
        assert px == py  # shared id across the two sessions
        memory_review.set_edited_text(sx, px, "X-ONLY edit", p["id"])
        memory_review.set_edited_text(sy, py, "Y-ONLY edit", p["id"])
        memory_review.approve_proposal(sx, px, p["id"])
        memory_review.approve_proposal(sy, py, p["id"])
        # each session kept its own edited text
        assert memory_review.build_proposals(sx, p["id"])[0]["edited_text"] == "X-ONLY edit"
        assert memory_review.build_proposals(sy, p["id"])[0]["edited_text"] == "Y-ONLY edit"
        # both reached memory, each traceable to its own session
        decisions = (profile_store.get_profile_memory_dir(p["id"]) / "decisions.md"
                     ).read_text(encoding="utf-8")
        assert "X-ONLY edit" in decisions and "Y-ONLY edit" in decisions
        assert f"- Source session: {sx}" in decisions
        assert f"- Source session: {sy}" in decisions


def test_approve_into_profile_a_never_touches_profile_b():
    with temp_env():
        a = profile_store.create_profile("A")
        b = profile_store.create_profile("B")
        profile_store.set_active_profile_id(a["id"])
        sid = _session(TWO, a["id"])
        props = memory_review.build_proposals(sid, a["id"])
        bmem = profile_store.get_profile_memory_dir(b["id"])
        b_before = {f.name: f.read_bytes() for f in bmem.glob("*.md")}
        memory_review.approve_proposal(sid, props[0]["proposal_id"], a["id"])
        b_after = {f.name: f.read_bytes() for f in bmem.glob("*.md")}
        assert b_before == b_after


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
