"""
Profile-scoped session archive.

Explicitly saved sessions (meeting/discussion/interview/work transcripts)
live under the OWNING profile:

    data/profiles/<profile-id>/sessions/<session-id>/
        metadata.json     <- schema, profile, mode, title, status fields
        transcript.txt    <- the visible transcript text (never audio)
        summary.json      <- structured summary, written when generated

Everything is local and gitignored (the whole data/ tree). Saving is an
explicit user action - nothing in this module is called automatically.

Safety:
- The profile is resolved through profile_store (fails closed when no
  profile is selected; unknown profiles raise).
- Callers never provide filesystem paths. Session ids are generated here
  (UTC timestamp + random suffix) and validated against a strict
  whitelist pattern before any read, so traversal ("..", slashes,
  absolute paths) is impossible by construction.
- Existing sessions are never overwritten.
- JSON writes are atomic (temp file + replace).
- This module NEVER touches profile memory files.

Stdlib only.
"""

import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from backend import profile_store
except ImportError:
    import profile_store

SCHEMA_VERSION = 1

# Session ids look like 20260613-094512-a3f9c2 (UTC time + random suffix).
_SESSION_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-f0-9]{6}$")


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sessions_root(profile_id=None):
    """Sessions directory for a profile (None = active, fail-closed)."""
    if profile_id is None:
        profile_id = profile_store.get_active_profile_id()
    # get_profile_memory_dir validates that the profile exists
    profile_dir = profile_store.get_profile_memory_dir(profile_id).parent
    return profile_dir / "sessions", profile_id


def _validate_session_id(session_id):
    if not isinstance(session_id, str) or not _SESSION_ID_RE.match(session_id):
        raise ValueError(f"Invalid session id: {session_id!r}")
    return session_id


def _atomic_write_json(path, data):
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _session_dir(session_id, profile_id=None, must_exist=True):
    _validate_session_id(session_id)
    root, profile_id = _sessions_root(profile_id)
    d = root / session_id
    if must_exist and not (d / "metadata.json").exists():
        raise ValueError(f"Unknown session for this profile: {session_id}")
    return d, profile_id


def _read_metadata(session_dir):
    with open(session_dir / "metadata.json", encoding="utf-8") as f:
        return json.load(f)


def _update_metadata(session_id, profile_id, **fields):
    d, _ = _session_dir(session_id, profile_id)
    meta = _read_metadata(d)
    meta.update(fields)
    meta["updated_at_utc"] = _utc_now()
    _atomic_write_json(d / "metadata.json", meta)
    return meta


def create_session(transcript, title=None, profile_id=None, mode_id=None):
    """Save a transcript as a new session under the profile. Explicit only.

    Rejects empty/whitespace transcripts. Never overwrites. Returns the
    metadata dict (including the generated session_id).
    """
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("Cannot save an empty transcript.")
    transcript = transcript.strip()

    root, profile_id = _sessions_root(profile_id)

    if mode_id is None:
        mode_id = profile_store.get_profile_mode(profile_id)
    else:
        # Normalize to a registered mode id (unknown ids fall back)
        try:
            from backend import mode_store
        except ImportError:
            import mode_store
        mode_id = mode_store.get_mode(mode_id)["id"]

    if not title or not str(title).strip():
        title = "Session " + datetime.now().strftime("%Y-%m-%d %H:%M")
    title = str(title).strip()[:120]

    # Generate a unique id; retry on the (unlikely) collision
    for _ in range(5):
        session_id = (time.strftime("%Y%m%d-%H%M%S", time.gmtime())
                      + "-" + secrets.token_hex(3))
        session_dir = root / session_id
        try:
            session_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            continue
    else:
        raise RuntimeError("Could not allocate a unique session id.")

    (session_dir / "transcript.txt").write_text(transcript, encoding="utf-8")

    meta = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "profile_id": profile_id,
        "mode_id": mode_id,
        "title": title,
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "summary_status": "pending",
        "memory_status": "not_reviewed",
    }
    _atomic_write_json(session_dir / "metadata.json", meta)
    return meta


def get_session(session_id, profile_id=None):
    """Return {'metadata': ..., 'summary': dict or None} for a session."""
    d, _ = _session_dir(session_id, profile_id)
    meta = _read_metadata(d)
    summary = None
    summary_path = d / "summary.json"
    if summary_path.exists():
        try:
            with open(summary_path, encoding="utf-8") as f:
                summary = json.load(f)
        except (json.JSONDecodeError, OSError):
            summary = None
    return {"metadata": meta, "summary": summary}


def get_transcript(session_id, profile_id=None):
    """Return the saved transcript text for a session."""
    d, _ = _session_dir(session_id, profile_id)
    return (d / "transcript.txt").read_text(encoding="utf-8")


def list_sessions(profile_id=None):
    """All sessions of ONE profile, newest first. Never crosses profiles."""
    root, _ = _sessions_root(profile_id)
    if not root.exists():
        return []
    sessions = []
    for entry in root.iterdir():
        if not entry.is_dir() or not _SESSION_ID_RE.match(entry.name):
            continue  # ignore anything that is not a valid session dir
        try:
            sessions.append(_read_metadata(entry))
        except (json.JSONDecodeError, OSError):
            continue  # unreadable metadata - skip rather than crash
    sessions.sort(key=lambda m: m.get("session_id", ""), reverse=True)
    return sessions


_MAX_TITLE_LEN = 120


def save_summary(session_id, summary, profile_id=None):
    """Store a generated summary and mark the session complete.

    If the summary carries a non-empty title, the session's metadata
    title is updated to it (capped) so Session History shows a
    descriptive name. The session id never changes.
    """
    if not isinstance(summary, dict):
        raise ValueError("Summary must be a dict.")
    d, profile_id = _session_dir(session_id, profile_id)
    _atomic_write_json(d / "summary.json", summary)
    fields = {"summary_status": "complete", "summary_error": ""}
    title = summary.get("title")
    if isinstance(title, str) and title.strip():
        fields["title"] = title.strip()[:_MAX_TITLE_LEN]
    return _update_metadata(session_id, profile_id, **fields)


def mark_summary_failed(session_id, error_message, profile_id=None):
    """Record a failed summary attempt. The transcript stays untouched."""
    return _update_metadata(
        session_id, profile_id,
        summary_status="failed",
        summary_error=str(error_message)[:300],
    )


def mark_summary_pending(session_id, profile_id=None):
    """Reset a session to pending (e.g. before a retry).

    Clears the prior error and keeps the transcript and any existing
    summary file - a retry will overwrite the summary if it succeeds.
    """
    return _update_metadata(session_id, profile_id,
                            summary_status="pending", summary_error="")
