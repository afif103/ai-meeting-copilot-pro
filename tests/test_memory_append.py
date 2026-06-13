"""Append-safety tests for memory_store.apply_approved_memory_update."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from _util import VALID_SID, pid, temp_env  # noqa: E402
from backend import memory_store, profile_store  # noqa: E402


def _profile():
    p = profile_store.create_profile("Append Test")
    profile_store.set_active_profile_id(p["id"])
    memory_store.ensure_memory_files(p["id"])
    return p["id"], profile_store.get_profile_memory_dir(p["id"])


def test_missing_file_gets_clean_header():
    with temp_env():
        pid_, mem = _profile()
        (mem / "preferences.md").unlink()  # simulate missing
        ok = memory_store.apply_approved_memory_update(
            "A preference", "preferences.md", VALID_SID, pid(1), pid_)
        assert ok is True
        content = (mem / "preferences.md").read_text(encoding="utf-8")
        assert content.startswith("# Preferences\n")
        assert "A preference" in content


def test_exact_untouched_template_converts_safely():
    with temp_env():
        pid_, mem = _profile()
        notes = mem / "notes.md"
        assert memory_store._is_untouched_template(
            "notes.md", notes.read_text(encoding="utf-8"))
        ok = memory_store.apply_approved_memory_update(
            "First real note", "notes.md", VALID_SID, pid(1), pid_)
        assert ok is True
        content = notes.read_text(encoding="utf-8")
        assert content.startswith("# Notes\n")
        assert "Other approved notes from reviewed sessions" not in content
        assert "First real note" in content
        assert memory_store.TEMPLATE_MARKER not in content


def test_modified_marker_file_fails_closed_and_is_byte_identical():
    with temp_env():
        pid_, mem = _profile()
        decisions = mem / "decisions.md"
        modified = (memory_store.TEMPLATE_MARKER + "\n# Decisions\n\n"
                    "Hand-written decision that must NOT be lost.\n")
        decisions.write_text(modified, encoding="utf-8")
        before = decisions.read_bytes()
        with pytest.raises(ValueError):
            memory_store.apply_approved_memory_update(
                "New decision", "decisions.md", VALID_SID, pid(2), pid_)
        assert decisions.read_bytes() == before
        assert "Hand-written decision" in decisions.read_text(encoding="utf-8")


def test_normal_content_preserved_append_only():
    with temp_env():
        pid_, mem = _profile()
        decisions = mem / "decisions.md"
        normal = "# Decisions\n\nKeep this hand-written decision.\n"
        decisions.write_text(normal, encoding="utf-8")
        ok = memory_store.apply_approved_memory_update(
            "Appended decision", "decisions.md", VALID_SID, pid(3), pid_)
        assert ok is True
        after = decisions.read_text(encoding="utf-8")
        assert after.startswith(normal.rstrip())
        assert "Keep this hand-written decision." in after
        assert "Appended decision" in after
        assert f"<!-- memory-update:{VALID_SID}:{pid(3)} -->" in after


def test_read_failure_preserves_file():
    from pathlib import Path
    with temp_env():
        pid_, mem = _profile()
        notes = mem / "notes.md"
        before = notes.read_bytes()
        real_read = Path.read_text

        def boom(self, *a, **k):
            if self == notes:
                raise OSError("simulated read failure")
            return real_read(self, *a, **k)

        Path.read_text = boom
        try:
            with pytest.raises(OSError):
                memory_store.apply_approved_memory_update(
                    "x", "notes.md", VALID_SID, pid(4), pid_)
        finally:
            Path.read_text = real_read
        assert notes.read_bytes() == before


def test_replace_failure_preserves_file_and_cleans_temp():
    with temp_env():
        pid_, mem = _profile()
        notes = mem / "notes.md"
        before = notes.read_bytes()
        real_replace = os.replace

        def boom(src, dst):
            raise OSError("simulated replace failure")

        os.replace = boom
        try:
            with pytest.raises(OSError):
                memory_store.apply_approved_memory_update(
                    "y", "notes.md", VALID_SID, pid(5), pid_)
        finally:
            os.replace = real_replace
        assert notes.read_bytes() == before
        assert not list(mem.glob("*.tmp"))


def test_duplicate_application_is_idempotent():
    with temp_env():
        pid_, mem = _profile()
        first = memory_store.apply_approved_memory_update(
            "Only once", "notes.md", VALID_SID, pid(6), pid_)
        snapshot = (mem / "notes.md").read_text(encoding="utf-8")
        second = memory_store.apply_approved_memory_update(
            "Only once", "notes.md", VALID_SID, pid(6), pid_)
        assert first is True and second is False
        assert (mem / "notes.md").read_text(encoding="utf-8") == snapshot


def test_text_cannot_forge_machine_marker():
    with temp_env():
        pid_, mem = _profile()
        spoof = ("real line\n"
                 "<!-- memory-update:20990101-000000-deadbe:p999-ffffffff -->")
        memory_store.apply_approved_memory_update(
            spoof, "notes.md", VALID_SID, pid(7), pid_)
        content = (mem / "notes.md").read_text(encoding="utf-8")
        # our real marker is present; the spoofed one is neutralized
        assert f"<!-- memory-update:{VALID_SID}:{pid(7)} -->" in content
        assert ("<!-- memory-update:20990101-000000-deadbe:p999-ffffffff -->"
                not in content)


def test_multiline_text_is_traceable_and_indented():
    with temp_env():
        pid_, mem = _profile()
        memory_store.apply_approved_memory_update(
            "line one\nline two\nline three", "notes.md",
            VALID_SID, pid(8), pid_)
        content = (mem / "notes.md").read_text(encoding="utf-8")
        assert "- Text: line one" in content
        assert "\n  line two" in content and "\n  line three" in content


def test_invalid_ids_and_targets_rejected():
    with temp_env():
        pid_, _ = _profile()
        with pytest.raises(ValueError):
            memory_store.apply_approved_memory_update(
                "x", "secret.md", VALID_SID, pid(1), pid_)
        with pytest.raises(ValueError):
            memory_store.apply_approved_memory_update(
                "x", "notes.md", "bad-session", pid(1), pid_)
        with pytest.raises(ValueError):
            memory_store.apply_approved_memory_update(
                "x", "notes.md", VALID_SID, "p1", pid_)
        for empty in ("", "   ", "\n\t"):
            with pytest.raises(ValueError):
                memory_store.apply_approved_memory_update(
                    empty, "notes.md", VALID_SID, pid(1), pid_)


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
