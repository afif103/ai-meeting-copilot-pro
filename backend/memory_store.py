"""
Local interview memory store (profile-aware).

Personas define HOW answers sound (behavior, style, length). These memory
files define WHAT is true (resume, projects, job context, stories), so
facts live in editable local files instead of being baked into prompts.

- Each profile has its own memory directory (see backend/profile_store.py):
  data/profiles/<id>/memory/. All of it is gitignored - private, local.
- Functions take an optional profile_id; None means the active profile.
  If the profile system is unavailable, the legacy data/memory directory
  is used as a safe fallback.
- Missing files are created as guided templates. Existing files are NEVER
  overwritten. Templates are neutral - they contain no personal facts.
- A file that still contains TEMPLATE_MARKER is treated as unfilled and is
  excluded from prompts, so placeholder text can never reach the LLM.
- build_memory_block() concatenates the filled files in priority order
  under a character budget, and reloads automatically when a file changes
  (no app restart needed).

Stdlib only.
"""

import os
from pathlib import Path

# Legacy single-user memory location (pre-profiles). Safe fallback when
# the profile system is unavailable; never deleted by this module.
LEGACY_MEMORY_DIR = Path(__file__).parent.parent / "data" / "memory"

# Test hook: when set, all functions use this directory directly.
_OVERRIDE_DIR = None

TEMPLATE_MARKER = "<!-- TEMPLATE - fill in and delete this line -->"

# Total character budget for the whole memory block (~1,600 tokens at the
# 6500 default). The app raises num_ctx for Ollama suggestion calls so the
# block fits alongside the persona, conversation context, and the answer
# (see OLLAMA_NUM_CTX_SUGGEST in backend/grok_client.py). Override with
# INTERVIEW_MEMORY_BUDGET_CHARS in .env - the app loads .env before this
# module is imported.
try:
    DEFAULT_MEMORY_BUDGET = int(os.getenv("INTERVIEW_MEMORY_BUDGET_CHARS", "6500"))
except ValueError:
    DEFAULT_MEMORY_BUDGET = 6500


def _memory_dir(profile_id=None):
    """Resolve the memory directory for a profile (None = active profile).

    FAIL CLOSED: once the profile system imports, errors propagate - an
    unknown profile id raises ValueError and registry problems raise
    rather than silently exposing the legacy (Rami) memory to another
    profile. The legacy data/memory fallback applies ONLY when the
    profile system itself is absent (pre-profile installs).
    """
    if _OVERRIDE_DIR is not None:
        return Path(_OVERRIDE_DIR)
    try:
        from backend import profile_store
    except ImportError:
        try:
            import profile_store
        except ImportError:
            # No profile system at all - backward-compatible legacy mode
            return LEGACY_MEMORY_DIR

    if profile_id is None:
        profile_id = profile_store.get_active_profile_id()
    return profile_store.get_profile_memory_dir(profile_id)


# Files in PRIORITY ORDER - this is also the injection order, and the
# character budget is spent top to bottom, so put what matters most for
# the next interview first. "cap" is the per-file character limit.
# Templates are NEUTRAL: new profiles start with guidance only, no facts.
MEMORY_FILES = [
    {
        "filename": "answer_rules.md",
        "title": "Answer rules (how I want answers shaped)",
        "cap": 800,
        "template": (
            TEMPLATE_MARKER + "\n"
            "# Answer Rules\n"
            "\n"
            "Write rules for how YOU want interview answers shaped, then delete\n"
            "the marker line at the top. Examples (replace with your own):\n"
            "\n"
            "- Keep answers 3-5 sentences unless asked to go deeper\n"
            "- Only use facts and numbers from these memory files\n"
            "- If I don't know something: say so honestly\n"
        ),
    },
    {
        "filename": "job_description.md",
        "title": "Target job / company context",
        "cap": 1200,
        "template": (
            TEMPLATE_MARKER + "\n"
            "# Target Job / Company\n"
            "\n"
            "Before each interview, paste the key parts of the job posting here\n"
            "and delete the marker line at the top. Useful things to include:\n"
            "\n"
            "- Company name and what they build\n"
            "- Role title and seniority\n"
            "- Required skills (so answers can emphasize matching experience)\n"
            "- Key responsibilities from the posting\n"
        ),
    },
    {
        "filename": "career_profile.md",
        "title": "Career profile",
        "cap": 800,
        "template": (
            TEMPLATE_MARKER + "\n"
            "# Career Profile\n"
            "\n"
            "A short elevator pitch about yourself, then delete the marker line\n"
            "at the top. Useful things to include:\n"
            "\n"
            "- Who I am professionally in 2-3 sentences\n"
            "- Years of experience and my career story\n"
            "- My strongest skills\n"
            "- What role I am looking for\n"
        ),
    },
    {
        "filename": "interview_stories.md",
        "title": "Interview stories (real, defensible)",
        "cap": 1400,
        "template": (
            TEMPLATE_MARKER + "\n"
            "# Interview Stories\n"
            "\n"
            "Write 2-4 REAL stories you can defend in follow-up questions, then\n"
            "delete the marker line at the top. Suggested structure per story:\n"
            "\n"
            "## A challenge or problem I solved\n"
            "- Situation, what I did, what changed after\n"
            "- Only use numbers that are real and you can explain\n"
            "\n"
            "## A teamwork story\n"
            "\n"
            "## A story I am proud of\n"
        ),
    },
    {
        "filename": "project_ai_storefront.md",
        "title": "Main project",
        "cap": 900,
        "template": (
            TEMPLATE_MARKER + "\n"
            "# Main Project\n"
            "\n"
            "Describe your most important project or work experience, then\n"
            "delete the marker line at the top. Useful things to include:\n"
            "\n"
            "- What it is and who it is for\n"
            "- What you personally did\n"
            "- Tools/technology used\n"
            "- Anything measurable you can defend\n"
        ),
    },
    {
        "filename": "project_meeting_copilot.md",
        "title": "Second project",
        "cap": 800,
        "template": (
            TEMPLATE_MARKER + "\n"
            "# Second Project\n"
            "\n"
            "Describe another project or work experience, then delete the\n"
            "marker line at the top. Same structure as the main project.\n"
        ),
    },
    {
        "filename": "resume.md",
        "title": "Resume",
        "cap": 1800,
        "template": (
            TEMPLATE_MARKER + "\n"
            "# Resume\n"
            "\n"
            "(Paste the plain text of your current resume or CV here, then\n"
            "delete the marker line at the top so it starts being used.)\n"
        ),
    },
]


def _ensure_files_in(mem_dir):
    """Create the directory and any missing template files. Never overwrites."""
    mem_dir.mkdir(parents=True, exist_ok=True)
    created = []
    for spec in MEMORY_FILES:
        path = mem_dir / spec["filename"]
        if not path.exists():
            path.write_text(spec["template"], encoding="utf-8")
            created.append(spec["filename"])
    return created


def ensure_memory_files(profile_id=None):
    """Create missing memory templates for a profile (None = active).

    Returns the list of filenames that were created.
    """
    return _ensure_files_in(_memory_dir(profile_id))


# Files that contain personal EXPERIENCE. answer_rules.md and
# job_description.md shape answers but hold no personal facts, so they
# alone do not make a profile ready for personal interview answers.
PERSONAL_FACT_FILES = (
    "resume.md",
    "career_profile.md",
    "interview_stories.md",
    "project_ai_storefront.md",
    "project_meeting_copilot.md",
)


def has_profile_facts(profile_id=None):
    """True if the profile has at least one filled personal-experience file.

    A file counts only when it exists, is non-empty, and no longer carries
    the template marker.
    """
    mem_dir = _memory_dir(profile_id)
    for name in PERSONAL_FACT_FILES:
        try:
            content = (mem_dir / name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if content and TEMPLATE_MARKER not in content:
            return True
    return False


def _truncate(text, cap):
    """Cut text at cap, preferring a line boundary, and mark the cut."""
    if len(text) <= cap:
        return text
    cut = text.rfind("\n", 0, cap)
    if cut < cap // 2:  # no usable line break - hard cut
        cut = cap
    return text[:cut].rstrip() + "\n[...truncated...]"


def _load_filled_sections(mem_dir, include_job_description=True):
    """Return (title, content) for files that are filled in (no marker)."""
    sections = []
    for spec in MEMORY_FILES:
        if spec["filename"] == "job_description.md" and not include_job_description:
            continue  # non-interview modes must not see old job postings
        path = mem_dir / spec["filename"]
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content or TEMPLATE_MARKER in content:
            continue  # unfilled template or empty - never inject
        sections.append((spec["title"], _truncate(content, spec["cap"])))
    return sections


_EMPTY_MEMORY_NOTE = (
    "(No memory files are filled in yet. Answer honestly from general "
    "experience. Do not invent specific numbers, names, or projects.)"
)

# Cache: rebuild only when a memory file changes (so edits apply live
# without restarting the app). The stamp includes the directory, so
# switching profiles invalidates it automatically.
_cache = {"stamp": None, "block": ""}


def _dir_stamp(mem_dir):
    stamp = [str(mem_dir)]
    for spec in MEMORY_FILES:
        path = mem_dir / spec["filename"]
        try:
            st = path.stat()
            stamp.append((spec["filename"], st.st_mtime_ns, st.st_size))
        except OSError:
            stamp.append((spec["filename"], None, None))
    return tuple(stamp)


def build_memory_block(profile_id=None, max_chars=None, include_job_description=True):
    """Build the memory text injected into {memory} persona prompts.

    profile_id None = the active profile; max_chars None = default budget.
    include_job_description False drops job_description.md (used by
    non-interview modes - see backend/mode_store.py uses_job_description).
    """
    if max_chars is None:
        max_chars = DEFAULT_MEMORY_BUDGET
    mem_dir = _memory_dir(profile_id)
    _ensure_files_in(mem_dir)

    # The flag is part of the cache stamp so switching modes can never
    # reuse a block built with the wrong job-description setting.
    stamp = (_dir_stamp(mem_dir), max_chars, include_job_description)
    if _cache["stamp"] == stamp:
        return _cache["block"]

    sections = _load_filled_sections(mem_dir, include_job_description)
    if not sections:
        block = _EMPTY_MEMORY_NOTE
    else:
        parts = []
        used = 0
        for title, content in sections:
            piece = f"## {title}\n{content}"
            if used + len(piece) > max_chars:
                remaining = max_chars - used
                if remaining > 200:  # only add a partial section if useful
                    parts.append(_truncate(piece, remaining))
                break
            parts.append(piece)
            used += len(piece) + 2
        block = "\n\n".join(parts)

    _cache["stamp"] = stamp
    _cache["block"] = block
    return block


if __name__ == "__main__":
    import sys
    import tempfile

    print("Testing memory_store (profile-aware)...")
    this = sys.modules[__name__]

    with tempfile.TemporaryDirectory() as tmp:
        this._OVERRIDE_DIR = Path(tmp) / "memory"

        # 1. Templates are created once, never overwritten
        created = ensure_memory_files()
        assert len(created) == len(MEMORY_FILES), created
        assert ensure_memory_files() == []
        print(f"[OK] created {len(created)} neutral template files")

        # 2. Fresh templates are all markered -> safe empty note
        block = build_memory_block()
        assert block == _EMPTY_MEMORY_NOTE
        assert TEMPLATE_MARKER not in block
        print("[OK] fresh profile produces the safe empty note")

        # 3. Filling files makes them appear, in priority order
        (this._OVERRIDE_DIR / "answer_rules.md").write_text(
            "# Answer Rules\n- Always answer in first person\n",
            encoding="utf-8",
        )
        (this._OVERRIDE_DIR / "project_ai_storefront.md").write_text(
            "# Main Project\nA inventory system I built with Python.\n",
            encoding="utf-8",
        )
        block = build_memory_block()
        assert "Always answer in first person" in block
        assert "inventory system" in block
        assert block.index("Answer rules") < block.index("Main project")
        assert "replace with your own" not in block
        print("[OK] live reload + priority order + marker exclusion work")

        # 4. Budget is respected
        small = build_memory_block(max_chars=400)
        assert len(small) <= 430, len(small)
        print("[OK] character budget respected")

        this._OVERRIDE_DIR = None
        _cache["stamp"] = None

    # Real resolution: active profile via profile_store (creates default
    # profile + migrates legacy memory on first ever run)
    d = _memory_dir()
    preview = build_memory_block()
    print(f"\nActive memory dir: {d}")
    print(f"Memory block: {len(preview)} chars")
    print("\nAll memory_store self-tests passed")
