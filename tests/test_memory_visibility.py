"""Memory-visibility tests: approved updates reach the Profile Copilot
block, existing facts remain, and job-description scoping is mode-correct.
Model-free (only build_memory_block, no live LLM call)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from _util import fake_summary, temp_env  # noqa: E402
from backend import (  # noqa: E402
    memory_review, memory_store, profile_store, session_store,
)

ALL_CATEGORIES = [
    {"category": "decision", "text": "DECIDE_MARKER ship v2", "reason": "r", "confidence": "high"},
    {"category": "ongoing_task", "text": "TASK_MARKER write docs", "reason": "r", "confidence": "high"},
    {"category": "preference", "text": "PREF_MARKER async standups", "reason": "r", "confidence": "high"},
    {"category": "project_context", "text": "PROJ_MARKER new module", "reason": "r", "confidence": "high"},
    {"category": "person_role", "text": "ROLE_MARKER tech lead", "reason": "r", "confidence": "high"},
]


def _rami_sized_profile():
    """A synthetic profile filled to roughly the old 6,500-char pressure."""
    p = profile_store.create_profile("Synthetic")
    profile_store.set_active_profile_id(p["id"])
    memory_store.ensure_memory_files(p["id"])
    mem = profile_store.get_profile_memory_dir(p["id"])
    (mem / "career_profile.md").write_text(
        "# Career Profile\nIMPORTANT_FACT senior engineer. " + ("filler. " * 35),
        encoding="utf-8")
    (mem / "interview_stories.md").write_text(
        "# Stories\n" + ("A real defensible story. " * 55), encoding="utf-8")
    (mem / "project_ai_storefront.md").write_text(
        "# Main\n" + ("Storefront FastAPI RLS detail. " * 28), encoding="utf-8")
    (mem / "resume.md").write_text(
        "# Resume\n" + ("Experience line. " * 100), encoding="utf-8")
    memory_store._cache["stamp"] = None
    return p["id"], mem


def test_all_approved_categories_appear_in_block():
    with temp_env():
        pid_, _ = _rami_sized_profile()
        m = session_store.create_session("t.", mode_id="meeting_discussion")
        session_store.save_summary(m["session_id"], fake_summary(ALL_CATEGORIES), pid_)
        for p in memory_review.build_proposals(m["session_id"], pid_):
            memory_review.approve_proposal(m["session_id"], p["proposal_id"], pid_)
        memory_store._cache["stamp"] = None
        block = memory_store.build_memory_block(pid_)
        for marker in ("DECIDE_MARKER", "TASK_MARKER", "PREF_MARKER",
                       "PROJ_MARKER", "ROLE_MARKER"):
            assert marker in block


def test_existing_facts_remain_after_approvals():
    with temp_env():
        pid_, _ = _rami_sized_profile()
        m = session_store.create_session("t.", mode_id="meeting_discussion")
        session_store.save_summary(m["session_id"], fake_summary(ALL_CATEGORIES), pid_)
        for p in memory_review.build_proposals(m["session_id"], pid_):
            memory_review.approve_proposal(m["session_id"], p["proposal_id"], pid_)
        memory_store._cache["stamp"] = None
        assert "IMPORTANT_FACT" in memory_store.build_memory_block(pid_)


def test_job_description_included_only_for_interview_modes():
    with temp_env():
        pid_, mem = _rami_sized_profile()
        (mem / "job_description.md").write_text(
            "# Job\nJOBDESC_MARKER role.", encoding="utf-8")
        memory_store._cache["stamp"] = None
        assert "JOBDESC_MARKER" in memory_store.build_memory_block(
            pid_, include_job_description=True)
        assert "JOBDESC_MARKER" not in memory_store.build_memory_block(
            pid_, include_job_description=False)


def test_budget_is_large_enough():
    assert memory_store.DEFAULT_MEMORY_BUDGET >= 9000


def test_newest_approved_update_visible_when_file_cap_exceeded():
    # Append enough approved decisions to blow past the decisions.md cap,
    # then confirm the NEWEST one is still in the injected block while the
    # base header survives and on-disk content is byte-stable for olds.
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        memory_store.ensure_memory_files(p["id"])
        mem = profile_store.get_profile_memory_dir(p["id"])

        cap = next(s["cap"] for s in memory_store.MEMORY_FILES
                   if s["filename"] == "decisions.md")
        # ~250 chars/block; enough blocks to exceed the cap several times
        n = (cap // 200) + 6
        for i in range(n):
            ok = memory_store.apply_approved_memory_update(
                f"DECISION_NUMBER_{i:03d} " + ("x" * 120),
                "decisions.md",
                "20260613-120000-aaaaaa", f"p{i + 1:03d}-aaaaaaaa", p["id"])
            assert ok is True

        disk = (mem / "decisions.md").read_text(encoding="utf-8")
        assert disk.count("## Memory update") == n  # all kept on disk

        memory_store._cache["stamp"] = None
        block = memory_store.build_memory_block(p["id"])
        newest = f"DECISION_NUMBER_{n - 1:03d}"
        oldest = "DECISION_NUMBER_000"
        assert newest in block          # newest survives truncation
        assert "# Decisions" in block   # base header preserved
        # the block section for decisions is within (roughly) its cap
        # (some old blocks omitted) -> the very oldest should be dropped
        assert oldest not in block
        assert "older memory update" in block  # omission is marked


def test_career_profile_base_and_newest_person_role_both_visible():
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        memory_store.ensure_memory_files(p["id"])
        mem = profile_store.get_profile_memory_dir(p["id"])
        # real base content (no marker) + several appended person_role updates
        (mem / "career_profile.md").write_text(
            "# Career Profile\nBASE_PITCH I am a senior engineer.\n",
            encoding="utf-8")
        for i in range(8):
            memory_store.apply_approved_memory_update(
                f"ROLE_UPDATE_{i:03d} " + ("y" * 120), "career_profile.md",
                "20260613-120000-aaaaaa", f"p{i + 1:03d}-bbbbbbbb", p["id"])
        memory_store._cache["stamp"] = None
        block = memory_store.build_memory_block(p["id"])
        assert "BASE_PITCH" in block             # base preserved
        assert "ROLE_UPDATE_007" in block        # newest visible


def test_marker_free_file_keeps_start_truncation():
    # A long marker-free file still truncates from the END (keeps start).
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        memory_store.ensure_memory_files(p["id"])
        mem = profile_store.get_profile_memory_dir(p["id"])
        cap = next(s["cap"] for s in memory_store.MEMORY_FILES
                   if s["filename"] == "resume.md")
        (mem / "resume.md").write_text(
            "# Resume\nSTART_MARKER\n" + ("filler line\n" * 400) + "END_MARKER\n",
            encoding="utf-8")
        memory_store._cache["stamp"] = None
        block = memory_store.build_memory_block(p["id"])
        assert "START_MARKER" in block      # start kept
        assert "END_MARKER" not in block    # end truncated (no markers)


# ---- _truncate_with_updates: newest-update prompt priority (direct) ----

def _file_with_blocks(base, texts):
    """Build file text: base + one memory-update block per text (oldest
    first, so texts[-1] is the newest)."""
    parts = [base]
    for i, t in enumerate(texts):
        marker = f"<!-- memory-update:20260613-120000-aaaaaa:p{i + 1:03d}-aaaaaaaa -->"
        parts.append(f"\n{marker}\n## Memory update\n- Text: {t}")
    return "".join(parts)


def test_trunc_long_base_still_shows_newest_update():
    base = "# Career Profile\nBASE_START " + ("z" * 2500) + " BASE_END"
    text = _file_with_blocks(base, ["ROLE_OLD aaa", "ROLE_NEW " + ("b" * 100)])
    cap = 1200
    out = memory_store._truncate_with_updates(text, cap)
    assert "BASE_START" in out          # base start preserved
    assert "ROLE_NEW" in out            # newest update shown despite long base
    assert len(out) <= cap + 80


def test_trunc_huge_newest_is_shown_truncated():
    text = _file_with_blocks("# Decisions\nBASEFACT",
                             ["NEWESTHUGE " + ("y" * 3000)])
    cap = 1000
    out = memory_store._truncate_with_updates(text, cap)
    assert "NEWESTHUGE" in out                    # newest represented...
    assert "newest update truncated" in out       # ...and marked truncated
    assert "older memory update" not in out        # not mislabeled as 'older'
    assert len(out) <= cap + 80


def test_trunc_older_small_not_preferred_over_newer_oversized():
    text = _file_with_blocks(
        "# Decisions\nBASEFACT",
        ["OLDSMALL tiny", "NEWHUGE " + ("y" * 3000)])  # newest is oversized
    cap = 1000
    out = memory_store._truncate_with_updates(text, cap)
    assert "NEWHUGE" in out               # newest (truncated) shown
    assert "newest update truncated" in out
    assert "OLDSMALL" not in out          # older small NOT shown in its place


def test_trunc_respects_cap_tolerance():
    text = _file_with_blocks("# H\nBASE", ["x" * 200 for _ in range(30)])
    cap = 1000
    out = memory_store._truncate_with_updates(text, cap)
    assert len(out) <= cap + 80           # within documented tolerance


def test_truncation_never_changes_disk_bytes():
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        memory_store.ensure_memory_files(p["id"])
        mem = profile_store.get_profile_memory_dir(p["id"])
        for i in range(20):
            memory_store.apply_approved_memory_update(
                f"DEC_{i:03d} " + ("x" * 150), "decisions.md",
                "20260613-120000-aaaaaa", f"p{i + 1:03d}-aaaaaaaa", p["id"])
        before = (mem / "decisions.md").read_bytes()
        memory_store._cache["stamp"] = None
        memory_store.build_memory_block(p["id"])  # truncates for the prompt
        assert (mem / "decisions.md").read_bytes() == before  # disk unchanged


def test_total_budget_respected_within_tolerance():
    with temp_env():
        p = profile_store.create_profile("R")
        profile_store.set_active_profile_id(p["id"])
        memory_store.ensure_memory_files(p["id"])
        mem = profile_store.get_profile_memory_dir(p["id"])
        # fill several files heavily
        for fname in ("decisions.md", "ongoing_tasks.md", "notes.md"):
            for i in range(15):
                memory_store.apply_approved_memory_update(
                    f"E_{i:03d} " + ("x" * 200), fname,
                    "20260613-120000-aaaaaa", f"p{i + 1:03d}-aaaaaaaa", p["id"])
        memory_store._cache["stamp"] = None
        block = memory_store.build_memory_block(p["id"])
        # total within budget plus a small per-section marker tolerance
        assert len(block) <= memory_store.DEFAULT_MEMORY_BUDGET + 300


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
