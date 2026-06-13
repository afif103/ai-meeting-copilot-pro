"""
Memory-update review: turn a session's suggested_memory_updates into
individually reviewable proposals, and apply only the ones the user
explicitly approves.

Nothing here is automatic. Proposals are built ONLY from the session's
summary.json -> suggested_memory_updates; no new facts are inferred.
Review state persists in the session folder so decisions survive restart:

    data/profiles/<profile-id>/sessions/<session-id>/memory_review.json

Approving a proposal calls memory_store.apply_approved_memory_update,
which appends (only) the approved/edited text to the mapped memory file
of the SAME profile. Rejecting writes nothing.

Stdlib only.
"""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone

try:
    from backend import memory_store, session_store
except ImportError:
    import memory_store
    import session_store

SCHEMA_VERSION = 1

_VALID_CATEGORIES = {"person_role", "project_context", "decision",
                     "ongoing_task", "preference", "other"}
_VALID_CONFIDENCE = {"high", "medium", "low"}
_VALID_DECISIONS = {"pending", "approved", "rejected"}
_PROPOSAL_ID_RE = re.compile(r"^p[0-9]{3}-[a-f0-9]{8}$")
# The summary schema written by backend/session_summary.py (SCHEMA_VERSION).
_SUMMARY_SCHEMA_VERSION = 1


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validated_suggestions(session_id, profile_id, review_exists):
    """Return the validated suggestion list, or None when there is nothing
    to build and nothing to persist.

    FAILS CLOSED (raises) so existing review decisions are never erased by
    a missing/unreadable/malformed summary:
      - summary present but unreadable / invalid JSON / not an object -> raise
        (handled by read_summary_strict);
      - no summary, but the session is 'complete' -> raise;
      - no summary, but review state already exists -> raise;
      - no summary and no review state (pending/failed) -> None (build nothing);
      - valid summary -> the suggestion list (possibly empty), with every
        entry strictly validated (a non-object or text-less suggestion
        raises rather than being silently skipped).
    """
    meta = session_store.get_session(session_id, profile_id)["metadata"]
    status = meta.get("summary_status")
    summary = session_store.read_summary_strict(session_id, profile_id)
    if summary is None:
        if status == "complete":
            raise ValueError(
                f"Session {session_id} is marked complete but its summary "
                "could not be loaded.")
        if review_exists:
            raise ValueError(
                f"Session {session_id} has existing review state but no "
                "loadable summary; refusing to erase prior decisions.")
        return None  # pending/failed, no review yet -> safe to build nothing
    # Summary envelope (the generation layer normalizes before saving, so
    # at this loading boundary we validate strictly and never coerce - a
    # silently-changed value could alter a stable proposal id and erase a
    # prior decision).
    if summary.get("schema_version") != _SUMMARY_SCHEMA_VERSION:
        raise ValueError(
            f"Session {session_id} summary has an unexpected schema_version: "
            f"{summary.get('schema_version')!r}")
    if "suggested_memory_updates" not in summary:
        raise ValueError(
            f"Session {session_id} summary is missing "
            "suggested_memory_updates.")
    sugg = summary["suggested_memory_updates"]
    if not isinstance(sugg, list):
        raise ValueError(
            f"Session {session_id} summary suggested_memory_updates is not "
            "a list.")
    for entry in sugg:
        if not isinstance(entry, dict):
            raise ValueError(
                f"Session {session_id} summary has a non-object suggestion.")
        for key in ("category", "text", "reason", "confidence"):
            if key not in entry:
                raise ValueError(
                    f"Session {session_id} summary suggestion is missing "
                    f"'{key}'.")
        category = entry["category"]
        if not isinstance(category, str) or category not in _VALID_CATEGORIES:
            raise ValueError(
                f"Session {session_id} summary suggestion has an invalid "
                f"category: {category!r}")
        text = entry["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError(
                f"Session {session_id} summary suggestion text must be a "
                "non-empty string.")
        reason = entry["reason"]
        if not isinstance(reason, str):  # empty string is allowed
            raise ValueError(
                f"Session {session_id} summary suggestion reason must be a "
                "string.")
        confidence = entry["confidence"]
        if not isinstance(confidence, str) or confidence not in _VALID_CONFIDENCE:
            raise ValueError(
                f"Session {session_id} summary suggestion has an invalid "
                f"confidence: {confidence!r}")
    return sugg


def _save(session_id, profile_id, proposals):
    path = session_store.session_review_path(session_id, profile_id)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "proposals": proposals,
    }
    # Unique temp file in the same dir, cleaned up on any failure, so a
    # failed write/replace leaves the previous review file untouched.
    fd, tmpname = tempfile.mkstemp(dir=str(path.parent), suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmpname, path)
    except Exception:
        try:
            os.unlink(tmpname)
        except OSError:
            pass
        raise
    session_store.set_memory_status(
        session_id, compute_status(proposals), profile_id)


def compute_status(proposals):
    """not_reviewed (all pending) / fully_reviewed (none pending) /
    partially_reviewed (mixed). Empty proposal list -> not_reviewed."""
    if not proposals:
        return "not_reviewed"
    pending = sum(1 for p in proposals if p.get("decision") == "pending")
    if pending == len(proposals):
        return "not_reviewed"
    if pending == 0:
        return "fully_reviewed"
    return "partially_reviewed"


def _load_prior_review_state(path, expected_session_id):
    """Read + strictly validate an existing memory_review.json.

    Returns {proposal_id: entry} for restoring prior decisions. FAILS
    CLOSED on anything wrong - unreadable, invalid JSON, a bad envelope
    (schema_version / session_id / proposals), a non-object proposal, a
    bad/duplicate proposal_id, a malformed field, or a decision/timestamp
    state that is internally inconsistent - by raising, so the caller
    never overwrites (and thus never silently erases) the existing file.
    No file -> empty prior state, which is valid.
    """
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise OSError(f"Could not read review state {path.name}: {e}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Review state {path.name} is not valid JSON: {e}")

    # ---- envelope ----
    if not isinstance(data, dict):
        raise ValueError(f"Review state {path.name} is not an object.")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Review state {path.name} has an unexpected schema_version: "
            f"{data.get('schema_version')!r}")
    sid = data.get("session_id")
    if not isinstance(sid, str) or sid != expected_session_id:
        raise ValueError(
            f"Review state {path.name} session_id mismatch: {sid!r}")
    if not isinstance(data.get("proposals"), list):
        raise ValueError(f"Review state {path.name} proposals is not a list.")

    # ---- proposals (our own saves always write all four keys) ----
    required = ("proposal_id", "decision", "edited_text", "applied_at_utc")
    prior = {}
    for entry in data["proposals"]:
        if not isinstance(entry, dict):
            raise ValueError(
                f"Review state {path.name} has a non-object proposal entry.")
        missing = [k for k in required if k not in entry]
        if missing:
            raise ValueError(
                f"Review state {path.name} proposal is missing required "
                f"field(s): {', '.join(missing)}")
        pid = entry["proposal_id"]
        if not isinstance(pid, str) or not _PROPOSAL_ID_RE.match(pid):
            raise ValueError(
                f"Review state {path.name} has an invalid proposal_id: {pid!r}")
        if pid in prior:
            raise ValueError(
                f"Review state {path.name} has a duplicate proposal_id: {pid}")
        decision = entry["decision"]
        if decision not in _VALID_DECISIONS:
            raise ValueError(
                f"Review state {path.name} has an invalid decision for "
                f"{pid}: {decision!r}")
        edited = entry["edited_text"]
        if not isinstance(edited, str):
            raise ValueError(
                f"Review state {path.name} has malformed edited_text for {pid}.")
        applied = entry["applied_at_utc"]
        # nullable, but if present must be a non-empty string
        if applied is not None and (
                not isinstance(applied, str) or not applied.strip()):
            raise ValueError(
                f"Review state {path.name} has malformed applied_at_utc "
                f"for {pid}.")
        # ---- decision / timestamp consistency ----
        if decision == "approved" and not (
                isinstance(applied, str) and applied.strip()):
            raise ValueError(
                f"Review state {path.name}: approved proposal {pid} has no "
                "applied_at_utc.")
        if decision in ("pending", "rejected") and applied is not None:
            raise ValueError(
                f"Review state {path.name}: {decision} proposal {pid} must "
                "have applied_at_utc=None.")
        prior[pid] = entry
    return prior


def _proposal_id(index, category, original, reason, confidence):
    """Stable id: position + digest of the normalized fields.

    Position keeps two identical suggestions distinct; the digest ties an
    id to its content so a restart with an unchanged summary restores the
    same ids, while a changed/reordered summary yields different ids
    (decisions never silently attach to the wrong proposal).
    """
    key = "\x1f".join([category, original, reason, confidence])
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    return f"p{index + 1:03d}-{digest}"


def build_proposals(session_id, profile_id=None):
    """Build (or reconcile) the review proposals for a session.

    Proposals come only from summary.json suggestions. Existing decisions,
    edits, and applied state are carried over by matching the stable
    proposal_id, so reviewing survives restarts and a changed/reordered
    summary cannot inherit the wrong decision. Always persists.
    """
    # FAIL CLOSED on a malformed existing review file (never overwrite it).
    path = session_store.session_review_path(session_id, profile_id)
    review_exists = path.exists()
    prior_by_id = _load_prior_review_state(path, session_id)

    # FAIL CLOSED on a missing/malformed summary when review state exists or
    # the session is complete (so decisions are never erased). None means
    # "nothing to build and nothing to persist".
    suggestions = _validated_suggestions(session_id, profile_id, review_exists)
    if suggestions is None:
        return []

    proposals = []
    for i, sugg in enumerate(suggestions):
        original = str(sugg.get("text", "")).strip()
        category = str(sugg.get("category", "other")).strip().lower()
        if category not in _VALID_CATEGORIES:
            category = "other"
        confidence = str(sugg.get("confidence", "low")).strip().lower()
        if confidence not in _VALID_CONFIDENCE:
            confidence = "low"
        reason = str(sugg.get("reason", "")).strip()

        pid = _proposal_id(i, category, original, reason, confidence)
        prior = prior_by_id.get(pid)  # restore state only on exact id match
        decision = prior.get("decision") if prior else "pending"
        if decision not in _VALID_DECISIONS:
            decision = "pending"
        edited = prior.get("edited_text") if prior else original
        if not isinstance(edited, str) or not edited.strip():
            edited = original
        applied = prior.get("applied_at_utc") if prior else None

        proposals.append({
            "proposal_id": pid,
            "category": category,
            "original_text": original,
            "edited_text": edited,
            "reason": reason,
            "confidence": confidence,
            "decision": decision,
            "target_file": memory_store.target_file_for_category(category),
            "applied_at_utc": applied,
        })

    _save(session_id, profile_id, proposals)
    return proposals


def _find(proposals, proposal_id):
    for p in proposals:
        if p["proposal_id"] == proposal_id:
            return p
    raise ValueError(f"Unknown proposal: {proposal_id!r}")


def set_edited_text(session_id, proposal_id, edited_text, profile_id=None):
    """Edit a proposal's text before approval (not allowed once applied)."""
    proposals = build_proposals(session_id, profile_id)
    p = _find(proposals, proposal_id)
    if p["applied_at_utc"]:
        raise ValueError("An applied proposal cannot be edited.")
    p["edited_text"] = str(edited_text)
    _save(session_id, profile_id, proposals)
    return proposals


def reject_proposal(session_id, proposal_id, profile_id=None):
    """Reject a proposal - writes nothing to permanent memory."""
    proposals = build_proposals(session_id, profile_id)
    p = _find(proposals, proposal_id)
    if p["applied_at_utc"]:
        raise ValueError("An applied proposal cannot be rejected.")
    p["decision"] = "rejected"
    _save(session_id, profile_id, proposals)
    return proposals


def reset_proposal(session_id, proposal_id, profile_id=None):
    """Return a pending/rejected proposal to pending (not once applied)."""
    proposals = build_proposals(session_id, profile_id)
    p = _find(proposals, proposal_id)
    if p["applied_at_utc"]:
        raise ValueError("An applied proposal cannot be reset.")
    p["decision"] = "pending"
    _save(session_id, profile_id, proposals)
    return proposals


def approve_proposal(session_id, proposal_id, profile_id=None):
    """Approve ONE proposal: append its edited text to the mapped memory
    file of this profile. Idempotent - never applies the same one twice."""
    proposals = build_proposals(session_id, profile_id)
    p = _find(proposals, proposal_id)
    if p["applied_at_utc"]:
        return proposals  # already applied - do not write again
    text = (p.get("edited_text") or "").strip()
    if not text:
        raise ValueError("Approved text cannot be empty.")

    memory_store.apply_approved_memory_update(
        text, p["target_file"], session_id, proposal_id, profile_id=profile_id)

    p["decision"] = "approved"
    p["applied_at_utc"] = _utc_now()
    _save(session_id, profile_id, proposals)
    return proposals
