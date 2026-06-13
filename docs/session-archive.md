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

## Suggested memory updates

The summary may include a **Suggested memory updates** section. These are
**proposals only** — nothing is added to your permanent profile memory in
this version. Reviewing and approving them into memory is a separate,
later feature (Packet 7B). They are stored only inside that session's
`summary.json`.

## Relationship to Save / Load

This profile session archive is **separate** from the existing
**Save** / **Load** buttons. Those export or import a single portable
session snapshot (transcript + history + metrics) to a file location you
choose, and are unchanged. The session archive instead keeps per-profile
sessions with structured summaries inside `data/profiles/`. The two
systems do not interfere with each other.
