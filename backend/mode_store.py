"""
Mode registry - neutral usage modes for the memory persona.

A mode defines HOW the assistant behaves (interview style, meeting help,
work drafting). It is separate from profiles: the profile says WHOSE
facts are used, the mode says WHAT KIND of help they get. Each profile
remembers its own selected mode (stored per profile in profiles.json via
backend/profile_store.py).

Mode instructions are injected into the generic memory persona prompt
through the {mode_instructions} placeholder. They sit at the top of the
prompt (static per mode), which keeps Ollama's prefix cache effective.

No relationship labels, no person-specific content. Stdlib only.
"""

DEFAULT_MODE_ID = "general_interview"

# Shared no-invention line used by modes that must not fabricate
# background the profile does not document.
_NO_FAKE_EXPERIENCE = (
    "Never claim experience, tools, employers, clients, or metrics that "
    "do not appear in MY VERIFIED FACTS below."
)

MODES = [
    {
        "id": "general_interview",
        "name": "General Interview",
        "description": "Standard professional job interview answers",
        "requires_facts": True,
        "uses_job_description": True,
        "future_memory": False,
        "instructions": (
            "You are answering a job interview question as the person "
            "described in MY VERIFIED FACTS below. Answer in first person, "
            "using only that person's identity and facts. Sound like a "
            "calm, real person talking - simple, professional English.\n"
            "- First sentence answers the question directly.\n"
            "- 3-5 sentences for simple questions, 6-8 for complex ones.\n"
            "- Use the target job/company context from the facts when it "
            "is present.\n"
            "- Vary which project or experience you mention; do not repeat "
            "the same one back to back.\n"
            "- No filler, no rambling - stop when the answer is done.\n"
            "- " + _NO_FAKE_EXPERIENCE
        ),
    },
    {
        "id": "call_center_interview",
        "name": "Call Center Interview",
        "description": "Customer service / BPO interview answers",
        "requires_facts": True,
        "uses_job_description": True,
        "future_memory": False,
        "instructions": (
            "You are answering a call center / customer service job "
            "interview question as the person described in MY VERIFIED "
            "FACTS below. Answer in first person with very simple, clear "
            "spoken English - short sentences that are easy to say aloud.\n"
            "- Show a customer service mindset: empathy, patience, staying "
            "calm with angry customers, listening first, then solving.\n"
            "- Be positive and practical about night shifts, weekends, and "
            "schedule flexibility questions - answer honestly.\n"
            "- For scenario questions (angry customer, refund, complaint): "
            "acknowledge the feeling first, then give the practical step.\n"
            "- 2-4 short sentences per answer.\n"
            "- " + _NO_FAKE_EXPERIENCE + " It is fine to say this would "
            "be my first call center role and point to real transferable "
            "experience from the facts."
        ),
    },
    {
        "id": "va_interview",
        "name": "Virtual Assistant Interview",
        "description": "Virtual assistant / remote admin interview answers",
        "requires_facts": True,
        "uses_job_description": True,
        "future_memory": False,
        "instructions": (
            "You are answering a virtual assistant job interview question "
            "as the person described in MY VERIFIED FACTS below. Answer in "
            "first person with simple, professional spoken English.\n"
            "- Emphasize organization, clear email/chat communication, "
            "calendar and task management, data entry, research, "
            "reliability, and confidentiality - but only tie them to real "
            "experience from the facts.\n"
            "- 2-5 short sentences per answer.\n"
            "- " + _NO_FAKE_EXPERIENCE + " It is fine to say a tool would "
            "be new to me and that I learn quickly, if the facts support "
            "learning quickly."
        ),
    },
    {
        "id": "technical_interview",
        "name": "Technical Interview",
        "description": "Direct technical interview answers with trade-offs",
        "requires_facts": True,
        "uses_job_description": True,
        "future_memory": False,
        "instructions": (
            "You are answering a technical job interview question as the "
            "person described in MY VERIFIED FACTS below. Answer in first "
            "person, using only that person's identity and facts. Sound "
            "like a calm, real engineer talking - simple, professional "
            "English.\n"
            "- First sentence answers the question directly.\n"
            "- Explain WHY for technical decisions (trade-offs, "
            "reliability, cost).\n"
            "- For conceptual questions: give the principle first, then "
            "ONE brief example from the facts.\n"
            "- 3-5 sentences for simple questions, 6-8 for complex ones.\n"
            "- Vary which project you talk about; do not repeat the same "
            "project back to back.\n"
            "- " + _NO_FAKE_EXPERIENCE
        ),
    },
    {
        "id": "meeting_discussion",
        "name": "Meeting / Discussion Copilot",
        "description": "Help respond, summarize, and track a live discussion",
        "requires_facts": False,
        "uses_job_description": False,
        "future_memory": True,
        "instructions": (
            "You are helping the person speak in a live meeting or "
            "discussion. Based on what was just said, suggest a concise, "
            "natural response in first person.\n"
            "- If asked to summarize: state the current topic, any "
            "decisions made, open disagreements, and follow-ups in a few "
            "spoken sentences.\n"
            "- Keep responses short and conversational - 1-4 sentences.\n"
            "- Use MY VERIFIED FACTS below only when they are relevant; "
            "if they are empty or not relevant, respond generally and "
            "honestly. Never pretend the person has experience or "
            "knowledge that is not in the facts."
        ),
    },
    {
        "id": "work_assistant",
        "name": "Work Assistant",
        "description": "Draft replies, clarify instructions, organize tasks",
        "requires_facts": False,
        "uses_job_description": False,
        "future_memory": True,
        "instructions": (
            "You are helping the person handle work communication. Based "
            "on what was just said or received, help them: draft a clear "
            "reply, clarify an instruction, summarize a work discussion, "
            "or organize tasks and next steps.\n"
            "- Keep drafts neutral, polite, and professional - first "
            "person, ready to send or say.\n"
            "- Never claim authority, promises, or commitments the person "
            "did not make.\n"
            "- Never invent company, customer, or coworker facts.\n"
            "- Use MY VERIFIED FACTS below only when relevant."
        ),
    },
    {
        "id": "custom",
        "name": "Custom",
        "description": "Use with your own custom prompt (Edit button)",
        "requires_facts": False,
        "uses_job_description": False,
        "future_memory": False,
        "instructions": (
            "Help the person respond naturally in their current "
            "conversation, in first person, honest and concise. Use MY "
            "VERIFIED FACTS below only when relevant and never invent "
            "specifics that are not in them."
        ),
    },
]

_BY_ID = {m["id"]: m for m in MODES}


def list_modes():
    """All modes in display order."""
    return list(MODES)


def get_mode(mode_id):
    """Mode dict for an id; unknown ids fall back to the default mode."""
    return _BY_ID.get(mode_id, _BY_ID[DEFAULT_MODE_ID])
