# Interview Trainer

The **Interview Trainer** is a simple, profile-scoped practice tool for
working through mock interview questions. This first version (Packet 8A) is a
**question flow only** — it shows practice questions you can read and page
through. It does not record audio, transcribe, or give AI feedback yet.

## Opening the Trainer

1. Select your **Profile** in the toolbar as usual.
2. Click **Trainer** in the toolbar.
3. A separate **Interview Trainer** window opens for the active profile.

If no profile is selected, the Trainer does not open and asks you to choose a
profile first.

## Choosing a track

Pick a **Track** from the dropdown:

- **Call Center** — customer-service / BPO style questions.
- **Virtual Assistant** — remote admin / VA style questions.

Changing the track shows that track's questions and returns you to the first
question.

## Choosing a difficulty

Pick a **Difficulty** from the dropdown:

- **Easy**, **Medium**, or **Hard**.

Each track and difficulty has **four** practice questions. Changing the
difficulty returns you to the first question.

## Simple English

The **Simple English** checkbox (on by default) shows a shorter,
plain-language version of the same question. Turning it off shows the standard
wording. Toggling it **keeps you on the same question** — only the wording
changes.

## Navigating questions

- **Next Question** and **Previous Question** move through the four questions.
- The label shows your position, e.g. **Question 1 of 4**.
- **Previous** is disabled on the first question; **Next** is disabled on the
  last question. Navigation never goes past the first or last question.
- **Close** closes the Trainer window.

## Profile-bound behavior

- The Trainer window belongs to the profile that was active when you opened it.
- If you switch to a different profile, the Trainer window **closes
  automatically**, so one profile's practice view is never left open under
  another profile.
- The Trainer's track, difficulty, and Simple English choices are **temporary
  window settings** — they are not saved, and they do **not** change the
  profile's selected copilot mode.

## Current limitations (Packet 8A)

This first version is intentionally small. It does **not** yet include:

- **No microphone recording** of your answers.
- **No transcription** of spoken answers.
- **No AI feedback, scoring, or improved sample answers.**
- **No session saving** — questions and any practice are not stored.

The questions are a fixed, built-in practice set (generic and synthetic).
Voice answers and AI feedback are planned for later Trainer updates.
