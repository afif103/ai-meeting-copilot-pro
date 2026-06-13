"""Shared helpers for the session-archive / memory-review test suite.

Not collected by pytest (no test_ prefix). Every test uses an isolated
temporary profile registry - never the real Rami profile or any personal
data.
"""

import contextlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend import memory_store, profile_store  # noqa: E402

# A session id and proposal id that match the strict store-side patterns,
# for tests that call apply_approved_memory_update directly.
VALID_SID = "20260613-120000-aaaaaa"


def pid(n):
    return f"p{n:03d}-{'a' * 8}"


@contextlib.contextmanager
def temp_env():
    """Point profile/memory storage at a throwaway temp dir, then restore."""
    real_dir = profile_store.PROFILES_DIR
    real_legacy = profile_store.LEGACY_MEMORY_DIR
    tmp = Path(tempfile.mkdtemp(prefix="copilot-test-"))
    profile_store.PROFILES_DIR = tmp / "profiles"
    profile_store.LEGACY_MEMORY_DIR = tmp / "no-legacy-here"
    memory_store._cache["stamp"] = None
    try:
        yield tmp
    finally:
        profile_store.PROFILES_DIR = real_dir
        profile_store.LEGACY_MEMORY_DIR = real_legacy
        memory_store._cache["stamp"] = None
        shutil.rmtree(tmp, ignore_errors=True)


def fake_summary(updates):
    """A minimal valid summary dict carrying the given memory-update list."""
    return {
        "schema_version": 1, "title": "T", "overview": "o",
        "key_points": [], "decisions": [], "action_items": [],
        "open_questions": [], "suggested_memory_updates": updates,
    }
