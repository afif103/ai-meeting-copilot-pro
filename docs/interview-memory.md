# Interview Memory

The **"Rami - Interview (Memory)"** persona separates two things that used
to be mixed together inside persona prompts:

- **The persona** controls *how* answers sound (length, tone, structure).
- **Memory files** control *what is true* (your resume, projects, the job
  you're interviewing for, your stories).

This means you update plain text files before an interview instead of
editing prompts — and the AI is told to use **only** the facts in those
files, never to invent metrics, names, or numbers.

## Privacy

Everything lives in `data/memory/` on this PC. The `data/` folder is
gitignored, so your personal facts are never committed or pushed. Nothing
is sent anywhere except to your local Ollama model.

## The memory files

Files are injected in this order (most important first — if the character
budget runs out, the bottom of the list gets truncated first):

| File | What to put in it | When to update |
|------|-------------------|----------------|
| `answer_rules.md` | Your personal rules for shaping answers ("keep it short", "lead with project X") | Rarely |
| `job_description.md` | The job posting, company, required stack, recruiter notes | **Before every interview** |
| `career_profile.md` | Your 2-3 sentence elevator pitch, strengths, target role | When your story changes |
| `interview_stories.md` | Real failure/conflict/success stories you can defend | Before interview rounds |
| `project_ai_storefront.md` | Facts about the SaaS/AI storefront platform | When the project grows |
| `project_meeting_copilot.md` | Facts about this copilot app | When the app grows |
| `resume.md` | Plain-text resume | When your resume changes |

## How to fill in a file

1. Open the file in any text editor (Notepad is fine).
2. Replace the guidance text with your real information.
3. **Delete the marker line at the top:**
   `<!-- TEMPLATE - fill in and delete this line -->`
4. Save. Done — no app restart needed; the next suggestion uses it.

The marker is the safety switch: a file that still contains it is treated
as "not filled in yet" and is **completely excluded** from prompts, so
template placeholder text can never leak into an interview answer.

Some files come pre-filled (no marker) from confirmed sources: the two
project files and `resume.md` (copied from `data/resume.txt`). Edit them
freely — your edits are never overwritten.

## Pre-interview checklist

1. Paste the job posting into `job_description.md`, delete its marker.
2. Skim `interview_stories.md` — are the stories right for this company?
3. Check `career_profile.md` still matches the role you're applying for.
4. In the app, select the persona **"Rami - Interview (Memory)"**.

## Rules the AI follows with this persona

- Facts come only from your memory files.
- If memory doesn't cover a question, it answers honestly and generally
  instead of inventing specifics.
- First sentence answers the question; 3-5 sentences for simple questions.
- Plain spoken English, no markdown.

## Limits worth knowing

- The whole memory block is capped (~6,500 characters by default,
  `INTERVIEW_MEMORY_BUDGET_CHARS` in `.env` to override). The app uses a
  larger context window for interview suggestions (`OLLAMA_NUM_CTX_SUGGEST`,
  default 8192) so the block fits. Keep files concise — bullet points beat
  paragraphs.
- **A real job post consumes memory budget.** A long posting in
  `job_description.md` squeezes lower-priority sections (resume is cut
  first). Paste the relevant parts of a posting, not the whole page.
- Each file also has its own cap (see `backend/memory_store.py`), so one
  huge file can't crowd out the others.
- The old personas ("Rami - AI Interview", etc.) still work unchanged but
  contain older baked-in facts; prefer the Memory persona once your files
  are filled in.
