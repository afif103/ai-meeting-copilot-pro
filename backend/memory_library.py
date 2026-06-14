"""
Read-only library of approved session-memory entries.

Parses ONLY the machine-marked blocks that Packet 7B's
memory_store.apply_approved_memory_update writes:

    <!-- memory-update:<session-id>:<proposal-id> -->
    ## Memory update — <UTC date>

    - Source session: <session-id>
    - Proposal: <proposal-id>
    - Approved at UTC: <ISO8601 Z>        (newer blocks only; optional)
    - Text: <approved text, possibly multiline indented by two spaces>

It NEVER writes, repairs, or deletes anything - it only reads. Every
malformed marker or incomplete/duplicate block is excluded and counted
as a warning (never attached to another entry, never mutated on disk).
Arbitrary Markdown headings and manual base content are not treated as
approved memory.

Profile resolution is strict (fails closed on no/ambiguous active profile,
raises on an unknown profile); it never falls back to legacy or another
profile.

Stdlib only.
"""

import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

try:
    from backend import memory_store, profile_store
except ImportError:
    import memory_store
    import profile_store

# Files Packet 7B appends approved entries to (read in a fixed order; this
# is only an append-index tiebreak, never the primary freshness signal).
_ORDERED_TARGETS = [
    "career_profile.md", "project_context.md", "decisions.md",
    "ongoing_tasks.md", "preferences.md", "notes.md",
]
_FILE_TO_CATEGORY = {v: k for k, v in memory_store.MEMORY_UPDATE_TARGETS.items()}

# Every machine marker starts with this prefix; we split on the prefix so
# a MALFORMED marker is detected (and warned about) rather than ignored.
_MARKER_PREFIX = "<!-- memory-update:"
_MARKER_LINE_RE = re.compile(
    r"^<!-- memory-update:([0-9]{8}-[0-9]{6}-[a-f0-9]{6}):"
    r"(p[0-9]{3}-[a-f0-9]{8}) -->$")
# Canonical reserved lines. Each must match its regex EXACTLY (full
# physical line). A line that begins with a reserved stem but does not
# match its canonical form makes the whole block malformed - it is never
# silently ignored.
#   heading: em-dash, single spaces, nothing trailing
#   source/proposal: a valid id, nothing trailing
#   approved-at: a canonical UTC timestamp (see _TS_RE)
#   text: "- Text:" then the (optional) first line of content
_HEADING_RE = re.compile(r"^## Memory update — (\d{4}-\d{2}-\d{2})$")
_SOURCE_RE = re.compile(r"^- Source session: ([0-9]{8}-[0-9]{6}-[a-f0-9]{6})$")
_PROPOSAL_RE = re.compile(r"^- Proposal: (p[0-9]{3}-[a-f0-9]{8})$")
_APPROVED_RE = re.compile(r"^- Approved at UTC: (.+)$")
_TEXT_RE = re.compile(r"^- Text:(?: (.*))?$")
# Reserved stems used to detect a malformed attempt at a reserved line.
_RESERVED_STEMS = (
    "## Memory update", "- Source session", "- Proposal",
    "- Approved at UTC", "- Text",
)
# Canonical approval timestamps: second precision, or microsecond with
# EXACTLY six fractional digits. UTC 'Z' only - no offsets, no non-UTC,
# no other fractional widths.
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?Z$")


def _valid_date(s):
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _parse_timestamp(s):
    """Parse an approval timestamp to a tz-aware UTC datetime, or None.
    Accepts ONLY canonical second or six-digit microsecond UTC 'Z' forms;
    rejects other fractional widths, offsets, and non-UTC."""
    if not isinstance(s, str) or not _TS_RE.match(s):
        return None
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in s else "%Y-%m-%dT%H:%M:%SZ"
    try:
        return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None  # impossible time component (e.g. hour 25)


def _session_ts(session_id):
    """Embedded YYYYMMDDHHMMSS from a session id, for legacy tiebreaking."""
    parts = session_id.split("-")
    if len(parts) >= 2:
        return parts[0] + parts[1]
    return ""


def _is_reserved_attempt(line):
    """True if a line begins with a reserved stem at column zero (so it is
    claiming to be a reserved field and must therefore match canonically).
    Two-space text continuations are indented, so they never trip this."""
    return any(line.startswith(stem) for stem in _RESERVED_STEMS)


def _parse_region(sid, pid, body):
    """Parse one block body into a record, or None if malformed.

    Strict: exactly one valid dated heading, exactly one Source session,
    one Proposal, one Text, at most one Approved-at-UTC; Source/Proposal
    must match the marker; multiline text only via two-space continuation;
    a real calendar date and (if present) a canonical timestamp whose day
    equals the heading day. Any duplicate reserved field, or any line that
    starts with a reserved stem but is NOT canonical, makes the block
    malformed (never silently ignored)."""
    lines = body.split("\n")
    headings, sources, proposals, approvals, texts = [], [], [], [], []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if ln.startswith("- Text"):  # canonical Text + 2-space continuation
            tm = _TEXT_RE.match(ln)
            if not tm:
                return None  # malformed Text line
            tl = [tm.group(1) or ""]
            j = i + 1
            while j < n and lines[j].startswith("  "):
                tl.append(lines[j][2:])
                j += 1
            texts.append("\n".join(tl).rstrip())
            i = j
            continue
        if ln.startswith("## Memory update"):
            hm = _HEADING_RE.match(ln)
            if not hm:
                return None
            headings.append(hm.group(1))
            i += 1
            continue
        if ln.startswith("- Source session"):
            sm = _SOURCE_RE.match(ln)
            if not sm:
                return None
            sources.append(sm.group(1))
            i += 1
            continue
        if ln.startswith("- Proposal"):
            pm = _PROPOSAL_RE.match(ln)
            if not pm:
                return None
            proposals.append(pm.group(1))
            i += 1
            continue
        if ln.startswith("- Approved at UTC"):
            am = _APPROVED_RE.match(ln)
            if not am:
                return None
            approvals.append(am.group(1))
            i += 1
            continue
        if _is_reserved_attempt(ln):
            return None  # a reserved stem we did not parse canonically
        i += 1

    # exactly-one reserved fields (no duplicates)
    if len(headings) != 1 or not _valid_date(headings[0]):
        return None
    if len(sources) != 1 or len(proposals) != 1 or len(texts) != 1:
        return None
    if len(approvals) > 1:
        return None
    if sources[0] != sid or proposals[0] != pid:
        return None
    text = texts[0]
    if not text.strip():
        return None
    date = headings[0]
    approved_at = None
    if approvals:
        ts_dt = _parse_timestamp(approvals[0])
        if ts_dt is None:
            return None  # malformed/non-canonical timestamp -> malformed
        if ts_dt.strftime("%Y-%m-%d") != date:
            return None  # timestamp day must match the heading day
        approved_at = approvals[0]
    return {"date": date, "text": text, "approved_at_utc": approved_at}


def _candidate_lines(text):
    """Physical-line spans (line_start, line_end) for every line that
    contains the marker PREFIX, de-duplicated and in order. Splitting on
    physical lines (not the raw prefix offset) means an inline/indented
    marker is judged as a whole line and can never absorb a preceding
    valid block."""
    spans = []
    seen = set()
    for m in re.finditer(re.escape(_MARKER_PREFIX), text):
        pos = m.start()
        line_start = text.rfind("\n", 0, pos) + 1  # 0 if no preceding newline
        if line_start in seen:
            continue  # two prefixes on one physical line -> handle once
        seen.add(line_start)
        nl = text.find("\n", pos)
        line_end = len(text) if nl < 0 else nl
        spans.append((line_start, line_end))
    return spans


def _parse_text(text, target_file):
    """Return (candidate_records, warning_count) for one file's content.

    Each marker is validated as a COMPLETE physical line (prefix at column
    zero, no leading/trailing text). A non-canonical marker line is one
    warning and no entry, and its region cannot attach to the preceding
    block."""
    records = []
    warnings = 0
    spans = _candidate_lines(text)
    for idx, (line_start, line_end) in enumerate(spans):
        marker_line = text[line_start:line_end]
        region_end = spans[idx + 1][0] if idx + 1 < len(spans) else len(text)
        # body is everything AFTER this physical line up to the next marker
        body = text[line_end + 1:region_end] if line_end < region_end else ""

        mm = _MARKER_LINE_RE.match(marker_line)
        if not mm:
            warnings += 1  # inline / indented / trailing-text marker
            continue
        sid, pid = mm.group(1), mm.group(2)
        rec = _parse_region(sid, pid, body)
        if rec is None:
            warnings += 1
            continue
        rec["session_id"] = sid
        rec["proposal_id"] = pid
        rec["target_file"] = target_file
        rec["category"] = _FILE_TO_CATEGORY.get(target_file, "other")
        records.append(rec)
    return records, warnings


def _sort_key(e):
    # Newest first, using PARSED tz-aware UTC datetimes (not string
    # compares). Primary: the exact approval timestamp when present; legacy
    # date-only blocks fall back to day-start, then the session-id
    # timestamp, then append position. Target-file order is never the
    # primary freshness signal.
    dt = _parse_timestamp(e["approved_at_utc"]) if e["approved_at_utc"] else None
    if dt is None:
        dt = datetime.strptime(e["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (dt, _session_ts(e["session_id"]), e["_read_index"])


# A canonical profile id as produced by profile_store.create_profile():
# lowercase [a-z0-9] groups joined by SINGLE hyphens, no leading/trailing
# hyphen. This deliberately matches collision-suffixed ids (e.g.
# "<40-char base>-2") which exceed the unsuffixed _MAX_ID_LEN - so length
# and sanitize-idempotence are NOT used here (sanitize truncates the
# suffix and would wrongly reject a legitimately generated id). The regex
# alone forbids separators, drives, UNC, colons, dots, traversal, spaces,
# uppercase, and repeated/edge hyphens. Registry membership is enforced
# separately by get_profile_memory_dir().
_PROFILE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_profile_id(profile_id):
    """Require a CANONICAL profile id BEFORE it is joined to any path, so a
    corrupt/malicious registry entry - absolute path, drive-qualified, UNC,
    traversal, separators, colon, dot segments, spaces, uppercase,
    leading/trailing or repeated hyphens - can never select an external
    path. Accepts every id create_profile() can generate, including
    collision suffixes longer than the unsuffixed id length limit."""
    if not isinstance(profile_id, str):
        raise ValueError("profile_id must be a string")
    if not _PROFILE_ID_RE.fullmatch(profile_id):
        raise ValueError(f"Invalid profile id: {profile_id!r}")
    return profile_id


def _is_junction(path):
    """Best-effort Windows junction / reparse-point detection, tolerant of
    Python versions without Path.is_junction(). Never raises."""
    try:
        return bool(path.is_junction())  # Python 3.12+
    except (AttributeError, OSError, ValueError):
        pass
    try:  # fallback: inspect the reparse-point attribute via lstat
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attrs & reparse)
    except (OSError, ValueError, AttributeError):
        return False


def _validate_profile_memory_dir(profile_id):
    """Validate the whole PROFILES_DIR/<id>/memory directory chain before
    any file is read. Returns one of:
        ("ok", mem_dir)   - trusted, safe to read
        ("missing", None) - chain plainly absent -> safe empty result
        ("rejected", None)- redirected/escaped/looped -> warn, read nothing

    Rejects a symlink/junction at either the profile or memory level, a
    non-directory, a chain that resolves outside the expected lexical path
    (escape or cross-profile redirection), and resolution loops/errors.
    Never reads through or mutates anything."""
    try:
        profiles_root_real = profile_store.PROFILES_DIR.resolve()
    except (OSError, RuntimeError):
        return ("rejected", None)
    profile_dir = profile_store.PROFILES_DIR / profile_id
    mem_dir = profile_dir / "memory"

    # Lexical containment FIRST (do not rely only on resolved equality): an
    # absolute/traversal id would make these parents differ before any I/O.
    if (profile_dir.parent != profile_store.PROFILES_DIR
            or mem_dir.parent != profile_dir):
        return ("rejected", None)

    # A symlink/junction at EITHER level is never "normal" - reject it
    # (caught before exists() so dangling links are rejected too).
    try:
        if (profile_dir.is_symlink() or mem_dir.is_symlink()
                or _is_junction(profile_dir) or _is_junction(mem_dir)):
            return ("rejected", None)
    except OSError:
        return ("rejected", None)

    # A genuinely-absent plain memory directory is a safe empty result.
    try:
        if not mem_dir.exists():
            return ("missing", None)
        if not profile_dir.is_dir() or not mem_dir.is_dir():
            return ("rejected", None)
    except OSError:
        return ("rejected", None)

    # The resolved chain must equal the expected lexical chain EXACTLY -
    # this catches redirection to another profile, escape outside the
    # profiles root, and (via the exception guard) resolution loops.
    try:
        if profile_dir.resolve() != profiles_root_real / profile_id:
            return ("rejected", None)
        if mem_dir.resolve() != profiles_root_real / profile_id / "memory":
            return ("rejected", None)
    except (OSError, RuntimeError):
        return ("rejected", None)
    return ("ok", mem_dir)


def _hard_link_count(path):
    """Hard-link count of `path`, NOT following symlinks. Isolated in its
    own function so the safety check can be exercised platform-
    independently in tests without monkeypatching os.lstat globally (which
    would break Path.resolve())."""
    return os.lstat(path).st_nlink


def _safe_regular_file(path, mem_dir_real):
    """Return True iff `path` is a real regular file living DIRECTLY inside
    the resolved profile memory dir, with EXACTLY one hard link. Rejects
    symlinks/junctions, anything resolving (through any redirection)
    outside the dir, and hard-linked files (st_nlink != 1) that would be a
    second name for another profile's / an external memory file. Never
    reads or mutates anything; a missing file returns False (the caller
    treats genuine absence separately, without a warning)."""
    try:
        if path.is_symlink():
            return False  # never follow a link, even one pointing "inside"
        resolved = path.resolve()
    except OSError:
        return False
    if resolved.parent != mem_dir_real:
        return False  # escaped the profile memory dir via redirection
    try:
        if resolved.is_symlink() or not resolved.is_file():
            return False
        # Hard-link guard: a count != 1 means the filename is a second
        # name for another file -> reject.
        if _hard_link_count(path) != 1:
            return False
    except OSError:
        return False
    return True


def read_approved_memory(profile_id=None):
    """Read a profile's approved session-memory entries (read-only).

    profile_id None = the active profile (fails closed if none/ambiguous).
    An unknown profile raises ValueError. Returns:
        {"profile_id": str, "entries": [record...], "warnings": int}
    Records: category, target_file, date, approved_at_utc (or None), text,
    session_id, proposal_id - newest first. Missing/unreadable files are
    skipped (unreadable ones add a warning); duplicate (session, proposal)
    markers are excluded and warned about.
    """
    if profile_id is None:
        profile_id = profile_store.get_active_profile_id()  # fail closed
    # Strict canonical id BEFORE any path construction / registry lookup,
    # so a corrupt registry entry can never select an external path.
    _validate_profile_id(profile_id)
    profile_store.get_profile_memory_dir(profile_id)  # validates id (raises)

    # Validate the whole profile/memory directory chain BEFORE trusting it
    # as a root: a redirected profile or memory dir must never expose
    # another profile's entries.
    status, mem_dir = _validate_profile_memory_dir(profile_id)
    if status == "missing":
        return {"profile_id": profile_id, "entries": [], "warnings": 0}
    if status != "ok":
        return {"profile_id": profile_id, "entries": [], "warnings": 1}
    mem_dir_real = mem_dir.resolve()  # safe: chain == expected lexical path

    candidates = []
    warnings = 0
    read_index = 0
    for target in _ORDERED_TARGETS:
        path = mem_dir / target
        # A genuinely absent optional file is safe and silent.
        if not path.is_symlink() and not path.exists():
            continue
        # Reject symlink/junction/redirected paths and non-regular files:
        # skip, warn, never expose contents, never modify the file/link.
        if not _safe_regular_file(path, mem_dir_real):
            warnings += 1
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            # unreadable (permissions) or invalid encoding - skip ONLY this
            # file, never repair it, keep showing the others
            warnings += 1
            continue
        recs, file_warnings = _parse_text(content, target)
        warnings += file_warnings
        for r in recs:
            r["_read_index"] = read_index
            read_index += 1
            candidates.append(r)

    # Exclude ambiguous duplicate (session_id, proposal_id) markers.
    counts = {}
    for r in candidates:
        counts[(r["session_id"], r["proposal_id"])] = \
            counts.get((r["session_id"], r["proposal_id"]), 0) + 1
    entries = []
    for r in candidates:
        if counts[(r["session_id"], r["proposal_id"])] > 1:
            warnings += 1  # ambiguous duplicate - exclude every copy
            continue
        entries.append(r)

    entries.sort(key=_sort_key, reverse=True)
    for e in entries:
        e.pop("_read_index", None)
    return {"profile_id": profile_id, "entries": entries, "warnings": warnings}
