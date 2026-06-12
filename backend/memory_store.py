"""
Local interview memory store.

Personas define HOW Rami answers (behavior, style, length). These memory
files define WHAT is true (resume, projects, job context, stories), so
facts live in editable local files instead of being baked into prompts.

- Files live in data/memory/ (gitignored - private, never leaves this PC).
- Missing files are created as guided templates. Existing files are NEVER
  overwritten.
- A file that still contains TEMPLATE_MARKER is treated as unfilled and is
  excluded from prompts, so placeholder text can never reach the LLM.
- build_memory_block() concatenates the filled files in priority order
  under a character budget, and reloads automatically when a file changes
  (no app restart needed).

Stdlib only.
"""

import os
from pathlib import Path

MEMORY_DIR = Path(__file__).parent.parent / "data" / "memory"

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


def _resume_seed():
    """Seed resume.md from the existing data/resume.txt when available."""
    resume_txt = MEMORY_DIR.parent / "resume.txt"
    if resume_txt.exists():
        try:
            content = resume_txt.read_text(encoding="utf-8").strip()
            if content:
                return "# Resume\n\n" + content + "\n"
        except OSError:
            pass
    return (
        TEMPLATE_MARKER + "\n"
        "# Resume\n"
        "\n"
        "(Paste the plain text of your current resume here, then delete the\n"
        "marker line at the top so the AI starts using it.)\n"
    )


# Files in PRIORITY ORDER - this is also the injection order, and the
# character budget is spent top to bottom, so put what matters most for
# the next interview first. "cap" is the per-file character limit.
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
            "- Lead with my AI storefront project for infrastructure questions\n"
            "- Mention my construction background only for teamwork/pressure questions\n"
            "- Never discuss salary expectations unless asked directly\n"
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
            "- Required tech stack (so answers can emphasize matching experience)\n"
            "- Key responsibilities from the posting\n"
            "- Anything from the recruiter call worth remembering\n"
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
            "- Years of experience and the career-change story (if asked)\n"
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
            "## A failure / hard bug story\n"
            "- Situation, what broke, what I did, what changed after\n"
            "- Only use numbers that are real and you can explain\n"
            "\n"
            "## A conflict / teamwork story\n"
            "\n"
            "## A story I am proud of\n"
        ),
    },
    {
        "filename": "project_ai_storefront.md",
        "title": "Project: multi-tenant SaaS / AI storefront",
        "cap": 900,
        "template": (
            "# Project: Multi-tenant SaaS / AI Storefront Platform\n"
            "\n"
            "- Multi-tenant SaaS platform with an AI storefront\n"
            "- FastAPI backend\n"
            "- PostgreSQL with tenant isolation / RLS (row-level security)\n"
            "- Redis\n"
            "- Next.js frontend\n"
            "- Product catalog and storefront\n"
            "- Orders, donations, pledges\n"
            "- POS order history, cancel, receipt reprint\n"
            "- Inventory tracking and stock movements\n"
            "- Analytics\n"
            "- AI assistant\n"
            "- AWS deployment: ECS Fargate, RDS, Redis, S3, CloudFront, WAF, ALB/HTTPS\n"
            "- Dev workflow: ChatGPT as architect/reviewer, Claude Code as implementer\n"
        ),
    },
    {
        "filename": "project_meeting_copilot.md",
        "title": "Project: AI Meeting Copilot (this app)",
        "cap": 800,
        "template": (
            "# Project: AI Meeting Copilot Pro\n"
            "\n"
            "- Local-first, privacy-focused interview/meeting copilot for Windows\n"
            "- Real-time audio capture (system audio via Voicemeeter, or microphone)\n"
            "- Offline speech-to-text with faster-whisper + voice activity detection\n"
            "- Local LLM suggestions via Ollama (default qwen3:8b) with native token streaming\n"
            "- Optional Groq cloud mode; local Ollama is the default\n"
            "- Disabled thinking mode for qwen3-family models to keep first-token latency low\n"
            "- ChromaDB vector store with per-user isolation for uploaded documents\n"
            "- Regex-based PII anonymizer runs before any prompt\n"
            "- Tkinter desktop UI: live transcript, streaming suggestions, session save/load, PDF/TXT export\n"
            "- Benchmarked local models for latency and quality (first token ~0.2-0.6s warm)\n"
            "- Dev workflow: ChatGPT as architect/reviewer, Claude Code as implementer\n"
        ),
    },
    {
        "filename": "resume.md",
        "title": "Resume",
        "cap": 1800,
        "template": _resume_seed,
    },
]


def ensure_memory_files():
    """Create data/memory and any missing files. Never overwrites.

    Returns the list of filenames that were created.
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    created = []
    for spec in MEMORY_FILES:
        path = MEMORY_DIR / spec["filename"]
        if not path.exists():
            template = spec["template"]
            if callable(template):
                template = template()
            path.write_text(template, encoding="utf-8")
            created.append(spec["filename"])
    return created


def _truncate(text, cap):
    """Cut text at cap, preferring a line boundary, and mark the cut."""
    if len(text) <= cap:
        return text
    cut = text.rfind("\n", 0, cap)
    if cut < cap // 2:  # no usable line break - hard cut
        cut = cap
    return text[:cut].rstrip() + "\n[...truncated...]"


def _load_filled_sections():
    """Return (title, content) for files that are filled in (no marker)."""
    sections = []
    for spec in MEMORY_FILES:
        path = MEMORY_DIR / spec["filename"]
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
# without restarting the app, but unchanged files cost 7 stat calls).
_cache = {"stamp": None, "block": ""}


def _dir_stamp():
    stamp = [str(MEMORY_DIR)]
    for spec in MEMORY_FILES:
        path = MEMORY_DIR / spec["filename"]
        try:
            st = path.stat()
            stamp.append((spec["filename"], st.st_mtime_ns, st.st_size))
        except OSError:
            stamp.append((spec["filename"], None, None))
    return tuple(stamp)


def build_memory_block(max_chars=DEFAULT_MEMORY_BUDGET):
    """Build the memory text injected into {memory} persona prompts."""
    ensure_memory_files()

    stamp = (_dir_stamp(), max_chars)
    if _cache["stamp"] == stamp:
        return _cache["block"]

    sections = _load_filled_sections()
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

    print("Testing memory_store...")
    this = sys.modules[__name__]
    real_dir = MEMORY_DIR

    with tempfile.TemporaryDirectory() as tmp:
        this.MEMORY_DIR = Path(tmp) / "memory"

        # 1. Templates are created once, never overwritten
        created = ensure_memory_files()
        assert len(created) == len(MEMORY_FILES), created
        assert ensure_memory_files() == []
        print(f"[OK] created {len(created)} files in temp dir")

        # 2. Marker files are excluded; seeded files are included
        block = build_memory_block()
        assert TEMPLATE_MARKER not in block
        assert "replace with your own" not in block  # template guidance text
        assert "FastAPI" in block, "storefront seed missing"
        assert "faster-whisper" in block, "copilot seed missing"
        print("[OK] marker files excluded, seeded facts included")

        # 3. Filling a file makes it appear, in priority order (first)
        (this.MEMORY_DIR / "answer_rules.md").write_text(
            "# Answer Rules\n- Always answer in first person\n",
            encoding="utf-8",
        )
        block = build_memory_block()
        assert "Always answer in first person" in block
        assert block.index("Answer rules") < block.index("FastAPI")
        print("[OK] live reload + priority order work")

        # 4. Budget is respected
        small = build_memory_block(max_chars=400)
        assert len(small) <= 430, len(small)
        print("[OK] character budget respected")

        # 5. Empty state has a safe note
        for spec in MEMORY_FILES:
            (this.MEMORY_DIR / spec["filename"]).write_text(
                TEMPLATE_MARKER, encoding="utf-8"
            )
        assert build_memory_block() == _EMPTY_MEMORY_NOTE
        print("[OK] empty memory produces a safe note")

    # Back to the real directory: create real files and show a preview
    this.MEMORY_DIR = real_dir
    _cache["stamp"] = None
    created = ensure_memory_files()
    print(f"\nReal dir: {MEMORY_DIR}")
    print(f"Created now: {created or '(all files already existed)'}")
    preview = build_memory_block()
    print(f"Memory block: {len(preview)} chars, starts with:")
    print(preview[:300])
    print("\nAll memory_store self-tests passed")
