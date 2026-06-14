"""Tests for the static Interview Trainer question bank (Packet 8A)."""

import dataclasses
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from backend import trainer_questions as tq  # noqa: E402

_TRACK_IDS = ("call_center", "virtual_assistant")
_DIFF_IDS = ("easy", "medium", "hard")


def test_exactly_two_tracks():
    tracks = tq.get_tracks()
    assert len(tracks) == 2
    assert tuple(t.id for t in tracks) == _TRACK_IDS


def test_exactly_three_difficulties():
    diffs = tq.get_difficulties()
    assert len(diffs) == 3
    assert tuple(d.id for d in diffs) == _DIFF_IDS


def test_exactly_four_questions_per_combo():
    for t in _TRACK_IDS:
        for d in _DIFF_IDS:
            qs = tq.get_questions(t, d)
            assert len(qs) == 4, f"{t}/{d} has {len(qs)}"


def test_twenty_four_unique_ids():
    ids = [q.id for t in _TRACK_IDS for d in _DIFF_IDS
           for q in tq.get_questions(t, d)]
    assert len(ids) == 24
    assert len(set(ids)) == 24  # all unique


def test_no_duplicate_question_ids():
    ids = [q.id for q in tq._QUESTIONS]
    assert len(ids) == len(set(ids)) == 24


def test_deterministic_ordering():
    for t in _TRACK_IDS:
        for d in _DIFF_IDS:
            first = [q.id for q in tq.get_questions(t, d)]
            second = [q.id for q in tq.get_questions(t, d)]
            assert first == second  # stable order across calls
    assert [t.id for t in tq.get_tracks()] == list(_TRACK_IDS)
    assert [d.id for d in tq.get_difficulties()] == list(_DIFF_IDS)


def test_wording_non_empty_and_distinct():
    for q in tq._QUESTIONS:
        assert q.normal.strip(), f"{q.id} empty normal"
        assert q.simple.strip(), f"{q.id} empty simple"
        assert q.normal != q.simple, f"{q.id} normal == simple"


def test_records_internally_consistent():
    for t in _TRACK_IDS:
        for d in _DIFF_IDS:
            for q in tq.get_questions(t, d):
                assert q.track == t
                assert q.difficulty == d
                assert q.id and isinstance(q.id, str)


def test_get_question_text_switches_on_simple_english():
    q = tq.get_questions("call_center", "easy")[0]
    assert tq.get_question_text(q, simple_english=False) == q.normal
    assert tq.get_question_text(q, simple_english=True) == q.simple


def test_unknown_track_rejected():
    with pytest.raises(ValueError):
        tq.get_questions("nope", "easy")


def test_unknown_difficulty_rejected():
    with pytest.raises(ValueError):
        tq.get_questions("call_center", "extreme")


def test_returned_collection_is_immutable_tuple():
    qs = tq.get_questions("virtual_assistant", "hard")
    assert isinstance(qs, tuple)
    with pytest.raises(AttributeError):
        qs.append(qs[0])  # tuples have no append -> cannot grow the bank


def test_question_records_are_frozen():
    q = tq.get_questions("call_center", "easy")[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.normal = "mutated"


def test_mutating_returned_data_does_not_change_bank():
    # take a reference, exhaust a list copy, confirm the bank is unchanged
    before = [q.id for q in tq.get_questions("call_center", "medium")]
    copy = list(tq.get_questions("call_center", "medium"))
    copy.clear()
    after = [q.id for q in tq.get_questions("call_center", "medium")]
    assert before == after
    assert len(tq._QUESTIONS) == 24


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
