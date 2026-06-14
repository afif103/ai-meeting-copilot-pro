# Session Archive

You can explicitly save a meeting, discussion, interview, or work session
under your selected profile, then generate a local structured summary for
later review. This is a manual action — nothing is saved automatically.

## How it works

1. Pick your **Profile** and **Mode** as usual.
2. Click **Save & Summarize** in the toolbar.
3. Confirm the privacy notice.
4. The visible transcript is saved immediately, then a structured summary
   is generated locally in the background (the app stays responsive).
5. When the summary is ready, a review window opens.

Click **Session History** to reopen any saved session for the active
profile.

## Privacy and safety

- **Local-first.** Sessions live on this PC only. Summaries are generated
  with your local Ollama model — the transcript is never sent to Groq or
  any cloud service, regardless of the Groq/Ollama toggle.
- **No audio is stored.** Only the transcript text already visible in the
  app is saved.
- **Permission matters.** Only save discussions you are allowed to store.
  Avoid confidential customer or company data unless your workplace
  permits it.

## Per-profile isolation

Each session belongs to the profile that was active when you saved it:

```
data/profiles/<profile-id>/sessions/<session-id>/
  metadata.json     <- title, profile, mode, timestamps, status
  transcript.txt    <- the saved transcript text
  summary.json      <- the structured summary (once generated)
```

Session History only ever shows the active profile's sessions. Switching
profiles switches the history source. The whole `data/` tree is
gitignored, so nothing here is committed or pushed.

## If summarization fails

If Ollama is unavailable or the summary can't be generated, the
**transcript is still saved**. The session is marked `failed`, and you
can reopen it from Session History and click **Retry Summary**. Retrying
can turn a failed session into a complete one without re-saving the
transcript.

## Suggested memory updates — review and approve

The summary may include a **Suggested memory updates** section. These are
**proposals only** — nothing reaches your permanent profile memory until
you explicitly approve it, one item at a time.

In a completed session's review window, click **Review Memory
Suggestions** to open the per-item review:

- Each proposal is shown separately with its category, confidence,
  reason, the original suggestion, and an **editable** approved text box.
- **Approve** writes only that one item, after a confirmation, to the
  mapped memory file of the current profile. **The edited text is what
  gets saved** — edit before approving if you want to change the wording.
- **Reject** writes nothing. **Reset to Pending** returns a rejected or
  pending item to pending.
- There is **no "approve all"** — every item needs its own decision.
- Approved items show **Applied** and cannot be applied again. Decisions
  persist across restarts.

Approved entries are appended (never overwriting existing content) in a
traceable block that records the source session, proposal, and the exact
approval time:

```
## Memory update — YYYY-MM-DD

- Source session: <session-id>
- Proposal: <proposal-id>
- Approved at UTC: YYYY-MM-DDTHH:MM:SS.ffffffZ
- Text: <approved or edited text>
```

The `Approved at UTC` line uses a canonical UTC timestamp with microsecond
precision, so entries approved within the same second still order
reliably. Blocks approved before this was introduced have no
`Approved at UTC` line (date-only); both forms remain supported and are
displayed correctly, newest first.

Approved meeting/work memory goes to neutral per-profile files
(`decisions.md`, `ongoing_tasks.md`, `preferences.md`, `notes.md`,
`project_context.md`); a person/role note goes to `career_profile.md`.
Once approved, the Profile Copilot can use the new memory immediately.

**Privacy still applies:** only approve facts you are allowed to keep.
Approving into one profile never touches another profile's memory, and if
you switch profiles the review actions are blocked until you switch back
to the session's own profile.

## Approved Memory (read-only library)

The **Approved Memory** button opens a read-only window listing the
entries you have approved into the active profile's memory, newest first.
Each entry shows its category and target file, the approval date, the
approved text (multiline preserved), and the source session and proposal
IDs it came from — so every approved fact stays traceable.

- **Local and profile-scoped:** it reads only the active profile's memory
  files; it never shows another profile's entries, and it closes when you
  switch profiles.
- **Read-only:** opening, refreshing, sorting, and closing it never change
  any file. It does not call Ollama or Groq.
- Only the machine-marked blocks written by the review/approval flow are
  listed; your own hand-written notes in those files are not shown as
  approved entries. Malformed/incomplete blocks are skipped and reported
  as a small "skipped" note rather than crashing the view.
- **Editing or deleting approved memory is not part of this view** — that
  is left to a separate future packet.

## Relationship to Save / Load

This profile session archive is **separate** from the existing
**Save** / **Load** buttons. Those export or import a single portable
session snapshot (transcript + history + metrics) to a file location you
choose, and are unchanged. The session archive instead keeps per-profile
sessions with structured summaries inside `data/profiles/`. The two
systems do not interfere with each other.
