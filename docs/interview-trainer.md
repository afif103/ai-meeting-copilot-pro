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

## Recording and transcribing your answer

Below the question is an **Your spoken answer** section:

1. Click **Start Answer** to begin recording from your microphone. The status
   changes to **Recording…** and the question controls lock while recording.
2. Speak your answer, then click **Stop Answer**.
3. The answer is transcribed **locally** (on this PC) with Faster-Whisper. The
   status shows **Transcribing locally…**, then **Transcript ready** with your
   text in the read-only box.
4. Click **Clear Answer** to remove the transcript and try again.

Notes:

- **Microphone only.** Answer recording always uses a **physical microphone**.
  Virtual / loopback inputs (for example **Voicemeeter**, VB-Cable, or
  "Stereo Mix") are **never** used to record your answer, so your spoken
  answer is never mixed with system or interviewer audio. If only a virtual
  device is available, recording is unavailable and the status says so — this
  does **not** change or interfere with the app's normal interview/system-audio
  (Voicemeeter) capture, which is left exactly as it is.
- **Manual only.** Recording never starts on its own — only when you press
  **Start Answer**. There is a safety limit of about **120 seconds** per
  recording; if reached, recording stops and transcription continues.
- **Changing the question clears the answer.** Moving to another question, or
  changing track or difficulty, clears the transcript (an answer belongs only
  to the question it was recorded for). Toggling **Simple English** keeps the
  transcript, because it is still the same question.
- **Nothing is kept.** The recorded audio uses a temporary file that is
  **deleted** after transcription (and on error, on clearing, on closing the
  window, or on a profile switch). Neither the audio nor the transcript is
  saved to your profile, sessions, or memory.
- **Profile-bound and safe.** Closing the Trainer or switching profiles stops
  any active recording and cancels the answer. If local transcription has not
  started yet, it is skipped entirely. If a local transcription is already
  running it cannot be force-stopped, but its result is **discarded** (never
  shown) and its temporary audio is deleted — nothing is delivered to a closed
  window.

## Current limitations (Packet 8B)

The Trainer can now show questions and record + transcribe a spoken answer. It
does **not** yet include:

- **No AI feedback** on your answer.
- **No scoring.**
- **No improved sample answer.**
- **No session saving** — questions, answers, and transcripts are not stored.
- **No memory updates** — nothing is written to profile memory.
- **No system-audio capture** for the Trainer (answers are microphone-only).
- **No cloud transcription** — transcription is always local.

The questions are a fixed, built-in practice set (generic and synthetic).
AI feedback and scoring are planned for a later Trainer update.
