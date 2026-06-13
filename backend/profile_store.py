"""
Local profile store - multiple people, completely separate memory.

Each profile owns an isolated memory directory:

    data/profiles/
        profiles.json          <- registry: profiles, active id, migration flag
        <profile-id>/
            profile.json       <- id + display name
            memory/            <- this profile's interview memory files

Everything lives under data/ (gitignored) - profile names and memory are
local and private, never committed.

Profiles use neutral labels only: a display name the person chooses
("Rami", "Ahmad", "Fatima", ...). No relationship labels.

The first run creates a default profile ("Rami") and migrates the legacy
data/memory files into it by COPYING - the legacy files are never modified
or deleted.

Stdlib only.
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

PROFILES_DIR = Path(__file__).parent.parent / "data" / "profiles"
LEGACY_MEMORY_DIR = Path(__file__).parent.parent / "data" / "memory"

DEFAULT_PROFILE_NAME = "Rami"

_MAX_ID_LEN = 40
_MAX_NAME_LEN = 60


def _registry_file():
    return PROFILES_DIR / "profiles.json"


def _load_registry():
    """Load the registry; a corrupt file is backed up and treated as empty."""
    path = _registry_file()
    if not path.exists():
        return {"active": None, "legacy_migrated": False, "profiles": {}}
    try:
        with open(path, encoding="utf-8") as f:
            reg = json.load(f)
        if not isinstance(reg, dict) or not isinstance(reg.get("profiles"), dict):
            raise ValueError("registry has unexpected shape")
        return reg
    except (json.JSONDecodeError, ValueError, OSError) as e:
        backup = path.with_suffix(".json.corrupt")
        try:
            shutil.copy2(path, backup)
            print(f"[WARN] profiles.json unreadable ({e}); backed up to {backup.name}")
        except OSError:
            pass
        return {"active": None, "legacy_migrated": False, "profiles": {}}


def _save_registry(reg):
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _registry_file().with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    tmp.replace(_registry_file())


def sanitize_profile_id(name):
    """Turn a display name into a stable, filesystem-safe lowercase slug.

    Only [a-z0-9-] can survive, so path traversal ("..", slashes, drive
    letters) is impossible by construction. Raises ValueError if nothing
    usable remains.
    """
    if not isinstance(name, str):
        raise ValueError("Profile name must be text.")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = slug[:_MAX_ID_LEN].strip("-")
    if not slug:
        raise ValueError(
            "Profile name must contain at least one letter or number."
        )
    return slug


def list_profiles():
    """Return [{'id', 'display_name'}] sorted by display name."""
    reg = _load_registry()
    items = [
        {"id": pid, "display_name": p.get("display_name", pid)}
        for pid, p in reg["profiles"].items()
    ]
    return sorted(items, key=lambda p: p["display_name"].lower())


def get_profile(profile_id):
    """Return {'id', 'display_name'} or None."""
    reg = _load_registry()
    p = reg["profiles"].get(profile_id)
    if p is None:
        return None
    return {"id": profile_id, "display_name": p.get("display_name", profile_id)}


def get_profile_memory_dir(profile_id):
    """Memory directory for a profile. The profile must exist."""
    reg = _load_registry()
    if profile_id not in reg["profiles"]:
        raise ValueError(f"Unknown profile: {profile_id!r}")
    return PROFILES_DIR / profile_id / "memory"


def create_profile(display_name):
    """Create a new profile with blank memory. Never overwrites.

    Display names must be unique (compared case-insensitively after
    stripping spaces) - a clear ValueError is raised otherwise. Different
    names that sanitize to the same slug get a -2/-3/... id suffix.
    Returns {'id', 'display_name'}.
    """
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("Profile name cannot be empty.")
    display_name = display_name.strip()[:_MAX_NAME_LEN]

    base = sanitize_profile_id(display_name)
    reg = _load_registry()

    wanted = display_name.casefold()
    for existing in reg["profiles"].values():
        if existing.get("display_name", "").strip().casefold() == wanted:
            raise ValueError(
                f"A profile named '{existing['display_name']}' already "
                "exists. Choose a different name."
            )

    profile_id = base
    n = 2
    while profile_id in reg["profiles"] or (PROFILES_DIR / profile_id).exists():
        profile_id = f"{base}-{n}"
        n += 1

    memory_dir = PROFILES_DIR / profile_id / "memory"
    memory_dir.mkdir(parents=True, exist_ok=False)

    profile = {"display_name": display_name,
               "created": datetime.now().isoformat(timespec="seconds")}
    with open(PROFILES_DIR / profile_id / "profile.json", "w",
              encoding="utf-8") as f:
        json.dump({"id": profile_id, **profile}, f, indent=2,
                  ensure_ascii=False)

    reg["profiles"][profile_id] = profile
    if not reg.get("active"):
        reg["active"] = profile_id
    _save_registry(reg)
    return {"id": profile_id, "display_name": display_name}


def get_active_profile_id():
    """Active profile id. FAILS CLOSED when ambiguous.

    Creates the default profile on first ever use. If the registry holds
    exactly one profile, it becomes active automatically. With MULTIPLE
    profiles and a missing/invalid active value, raises ValueError - the
    user must select a profile explicitly; nobody's memory is silently
    exposed to someone else.
    """
    ensure_default_profile()
    reg = _load_registry()
    active = reg.get("active")
    if active in reg["profiles"]:
        return active
    if len(reg["profiles"]) == 1:
        only = next(iter(reg["profiles"]))
        reg["active"] = only
        _save_registry(reg)
        return only
    raise ValueError(
        "No active profile selected. Please select a profile before "
        "using profile memory."
    )


def set_active_profile_id(profile_id):
    reg = _load_registry()
    if profile_id not in reg["profiles"]:
        raise ValueError(f"Unknown profile: {profile_id!r}")
    if reg.get("active") != profile_id:
        reg["active"] = profile_id
        _save_registry(reg)


DEFAULT_MODE_ID = "general_interview"


def _is_known_mode(mode_id):
    """Check a mode id against the mode registry (local import - no cycle)."""
    try:
        from backend import mode_store
    except ImportError:
        try:
            import mode_store
        except ImportError:
            return True  # mode system absent - accept (legacy tolerance)
    return mode_store.get_mode(mode_id)["id"] == mode_id


def get_profile_mode(profile_id=None):
    """Selected mode id for a profile (None = active profile).

    Stored per profile, so switching profiles restores each person's own
    mode. Profiles without a saved mode default to the general interview.
    A corrupted/unknown saved mode is repaired to the general default -
    mode corruption is not identity corruption, so no fail-closed here.
    """
    if profile_id is None:
        profile_id = get_active_profile_id()
    reg = _load_registry()
    if profile_id not in reg["profiles"]:
        raise ValueError(f"Unknown profile: {profile_id!r}")
    saved = reg["profiles"][profile_id].get("mode", DEFAULT_MODE_ID)
    if not _is_known_mode(saved):
        print(f"[WARN] Profile '{profile_id}' had unknown mode "
              f"{saved!r} - repaired to '{DEFAULT_MODE_ID}'")
        reg["profiles"][profile_id]["mode"] = DEFAULT_MODE_ID
        _save_registry(reg)
        saved = DEFAULT_MODE_ID
    return saved


def set_profile_mode(mode_id, profile_id=None):
    """Save the selected mode for a profile (None = active profile).

    Unknown mode ids are rejected with a clear ValueError.
    """
    if not isinstance(mode_id, str) or not mode_id.strip():
        raise ValueError("Mode id cannot be empty.")
    mode_id = mode_id.strip()
    if not _is_known_mode(mode_id):
        raise ValueError(f"Unknown mode: {mode_id!r}")
    if profile_id is None:
        profile_id = get_active_profile_id()
    reg = _load_registry()
    if profile_id not in reg["profiles"]:
        raise ValueError(f"Unknown profile: {profile_id!r}")
    if reg["profiles"][profile_id].get("mode") != mode_id:
        reg["profiles"][profile_id]["mode"] = mode_id
        _save_registry(reg)


def ensure_default_profile():
    """First-run setup: create the default profile and migrate legacy memory.

    Migration COPIES files from data/memory into the default profile's
    memory dir (only when the destination file does not exist). The legacy
    files are never modified or deleted. Runs once, guarded by the
    'legacy_migrated' flag in the registry.
    """
    reg = _load_registry()

    if not reg["profiles"]:
        created = create_profile(DEFAULT_PROFILE_NAME)
        reg = _load_registry()
        reg["active"] = created["id"]
        _save_registry(reg)

    if not reg.get("legacy_migrated"):
        reg = _load_registry()
        target_id = reg.get("active") or next(iter(reg["profiles"]))
        target_dir = PROFILES_DIR / target_id / "memory"
        target_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        if LEGACY_MEMORY_DIR.exists():
            for src in sorted(LEGACY_MEMORY_DIR.glob("*.md")):
                dst = target_dir / src.name
                if not dst.exists():
                    shutil.copy2(src, dst)
                    copied.append(src.name)
        reg["legacy_migrated"] = True
        _save_registry(reg)
        if copied:
            print(f"[OK] Migrated legacy memory into profile "
                  f"'{target_id}': {', '.join(copied)}")

    return _load_registry().get("active")
