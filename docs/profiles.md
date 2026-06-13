# Profiles

Multiple people can use the app on the same PC, each with completely
separate, private interview memory. Profiles use neutral labels — just a
name the person chooses ("Rami", "Ahmad", "Fatima", …). The app never
asks for or stores relationship labels.

## Adding and selecting a profile

- The **Profile** dropdown in the top bar shows all profiles. Selecting
  one switches the active profile immediately — no restart needed. The
  Profile Copilot (Memory) persona reads the selected profile's memory
  from the very next suggestion.
- **Add Profile** asks for a display name, creates the profile with blank
  guided memory templates, and selects it. Invalid names (empty, or
  nothing usable in them) show an error. Names must be unique — "Rami"
  and "rami" count as the same name and are rejected with a clear
  message. Different names that happen to simplify to the same internal
  id are fine; the id gets a unique suffix automatically.

Persona selection is separate from profiles: the persona controls *how*
answers sound, the profile controls *whose facts* are used.

## Where profile memory lives

```
data/profiles/
  profiles.json           <- profile list + which one is active
  <profile-id>/
    profile.json          <- display name
    memory/               <- this profile's 7 memory files
```

Each profile's `memory/` works exactly like the original memory system
(same files, template markers, caps — see docs/interview-memory.md).
Edit the files of the profile you care about; each profile's job
description, stories, and resume are completely independent.

## Privacy

The whole `data/` folder is gitignored. Profile names, the registry, and
every memory file stay on this PC and are never committed or pushed.

## How the original (Rami) memory was migrated

On first run after this feature, the app creates a default profile named
"Rami" and **copies** the existing `data/memory/` files into
`data/profiles/rami/memory/`. The legacy `data/memory/` files are left
untouched as a backup — nothing is deleted or modified. The migration
runs once (a flag in `profiles.json` remembers it) and never overwrites
files that already exist in the profile.

## Modes

The **Mode** dropdown (next to Profile) controls what kind of help you
get. Selecting a standard mode automatically activates the generic
**Profile Copilot (Memory)** persona; selecting **Custom** activates the
existing Custom Prompt persona (Edit button). Each profile remembers its
own mode — switching profiles restores that person's last selection and
the matching persona. You can still pick an old persona manually
afterward.

Job descriptions (`job_description.md`) are used **only by interview
modes** — Meeting / Discussion Copilot and Work Assistant never receive
old interview job postings in their context.

| Mode | What it does | Needs filled memory? |
|------|--------------|----------------------|
| General Interview | Standard professional interview answers | Yes |
| Call Center Interview | Simple spoken English, customer-service mindset | Yes |
| Virtual Assistant Interview | Organization/communication/admin emphasis | Yes |
| Technical Interview | Direct answers with trade-offs (previous default behavior) | Yes |
| Meeting / Discussion Copilot | Concise responses, topic summaries, follow-ups | No (profile must be selected) |
| Work Assistant | Draft replies, clarify instructions, organize tasks | No (profile must be selected) |
| Custom | Neutral behavior for use with your own custom prompt | No |

Interview modes keep the safety rule: with no filled memory files the
persona answers deterministically that profile details have not been
added yet — it never invents experience. No mode ever claims experience,
tools, or employers that are not in the profile's memory files.

Conversation/meeting auto-memory is a separate planned feature — modes do
not save anything automatically yet.

## Saving sessions

You can explicitly save a transcript under your profile and generate a
local structured summary — see [session-archive.md](session-archive.md).
Saving is always a manual action and sessions are isolated per profile.

A completed summary's suggested memory updates are **proposals only**:
you review each one and **explicitly approve, edit, or reject** it before
anything is written to permanent memory. There is no automatic approval
and no "approve all" — and approving only ever writes into the session's
own profile. See [session-archive.md](session-archive.md) for details.
