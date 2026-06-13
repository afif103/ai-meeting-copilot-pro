"""
Structured session summaries via LOCAL Ollama only.

generate_session_summary(transcript, mode_id) returns a normalized dict:

{
  "schema_version": 1,
  "title": str, "overview": str,
  "key_points": [str],
  "decisions": [{"decision": str, "status": "confirmed|proposed|unclear"}],
  "action_items": [{"task": str, "owner": str, "due_date": str,
                    "status": "open"}],
  "open_questions": [str],
  "suggested_memory_updates": [{"category": ..., "text": str,
                                "reason": str, "confidence": ...}]
}

Guarantees:
- Always local: calls grok_client._call_ollama directly, so the Groq/cloud
  toggle is irrelevant and no transcript ever leaves this machine.
- think:false for qwen3-family models (handled inside _call_ollama).
- The model is asked for JSON (Ollama format=json); markdown fences are
  stripped defensively; <think> blocks are removed from every string.
- Every field is validated and normalized: missing -> safe empty values,
  missing owner -> "Unassigned", missing due date -> "Not specified",
  unknown enums -> safe defaults. Wrong shapes are dropped, not invented.
- If the model output cannot be parsed, SummaryError is raised - no
  fabricated summary is ever returned.
"""

import json
import re

try:
    from backend.grok_client import (
        OLLAMA_MODEL_SUGGEST,
        OLLAMA_NUM_CTX_SUGGEST,
        _call_ollama,
    )
except ImportError:
    from grok_client import (
        OLLAMA_MODEL_SUGGEST,
        OLLAMA_NUM_CTX_SUGGEST,
        _call_ollama,
    )

SCHEMA_VERSION = 1

# Keep the prompt inside the suggestion context window: transcript chars
# beyond this are trimmed from the middle (start and end usually carry
# the setup and the conclusions).
_MAX_TRANSCRIPT_CHARS = 12000
_SUMMARY_MAX_TOKENS = 1200

_DECISION_STATUSES = {"confirmed", "proposed", "unclear"}
_CONFIDENCES = {"high", "medium", "low"}
_CATEGORIES = {"person_role", "project_context", "decision",
               "ongoing_task", "preference", "other"}

_MODE_EMPHASIS = {
    "meeting_discussion": (
        "Emphasize: decisions made, disagreements, action items, and "
        "open questions."
    ),
    "work_assistant": (
        "Emphasize: instructions given, tasks, responsibilities, and "
        "follow-ups."
    ),
}
_INTERVIEW_EMPHASIS = (
    "Emphasize: questions asked, answers given, feedback topics, and "
    "follow-ups."
)


class SummaryError(Exception):
    """Raised when a valid summary could not be generated."""


def _truncate_transcript(text):
    text = text.strip()
    if len(text) <= _MAX_TRANSCRIPT_CHARS:
        return text
    head = text[: _MAX_TRANSCRIPT_CHARS // 3]
    tail = text[-(_MAX_TRANSCRIPT_CHARS * 2 // 3):]
    return head + "\n[...transcript truncated...]\n" + tail


def _build_prompt(transcript, mode_id):
    if mode_id in _MODE_EMPHASIS:
        emphasis = _MODE_EMPHASIS[mode_id]
    elif isinstance(mode_id, str) and "interview" in mode_id:
        emphasis = _INTERVIEW_EMPHASIS
    else:
        emphasis = "Produce a neutral, factual structured summary."

    return (
        "You are a precise summarizer. Read the transcript and respond "
        "with ONLY one JSON object using exactly these keys:\n"
        '- "title": short descriptive title, max 12 words\n'
        '- "overview": 2-4 factual sentences\n'
        '- "key_points": array of short strings\n'
        '- "decisions": array of {"decision": string, "status": '
        '"confirmed" or "proposed" or "unclear"}. Use "confirmed" ONLY '
        "when the transcript clearly shows agreement; proposals and "
        'unresolved ideas are "proposed" or "unclear".\n'
        '- "action_items": array of {"task": string, "owner": string '
        '(use "Unassigned" when nobody is named), "due_date": string '
        '(exact or relative wording from the transcript, or "Not '
        'specified"), "status": "open"}\n'
        '- "open_questions": array of short strings\n'
        '- "suggested_memory_updates": array of {"category": one of '
        '"person_role","project_context","decision","ongoing_task",'
        '"preference","other", "text": string, "reason": string, '
        '"confidence": "high" or "medium" or "low"} - long-term facts '
        "worth remembering, as PROPOSALS only.\n"
        "Rules: use ONLY information from the transcript. Never invent "
        "names, owners, dates, projects, or outcomes. Keep every entry "
        "short - do not copy long transcript passages. "
        + emphasis + "\n\n"
        "TRANSCRIPT:\n" + _truncate_transcript(transcript) + "\n\nJSON:"
    )


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _clean_text(value, cap):
    """Coerce to a clean single string with a length cap."""
    if not isinstance(value, str):
        return ""
    value = _THINK_RE.sub("", value)
    value = value.replace("<think>", "").replace("</think>", "").strip()
    return value[:cap]


def _parse_model_json(text):
    """Parse model output into a dict; tolerate fences and stray prose."""
    if not text:
        raise SummaryError("The local model returned no output.")
    text = _THINK_RE.sub("", text)
    text = _FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Last resort: the outermost {...} block
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise SummaryError("The local model did not return valid JSON.")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            raise SummaryError("The local model did not return valid JSON.")
    if not isinstance(data, dict):
        raise SummaryError("The local model returned JSON of the wrong shape.")
    return data


def _str_list(value, cap_each=400, cap_items=12):
    out = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):  # some models wrap strings
                item = item.get("text") or item.get("point") or ""
            s = _clean_text(item, cap_each)
            if s:
                out.append(s)
            if len(out) >= cap_items:
                break
    return out


def _normalize(raw):
    """Validate/normalize a parsed model dict into the summary schema."""
    summary = {
        "schema_version": SCHEMA_VERSION,
        "title": _clean_text(raw.get("title"), 120) or "Untitled session",
        "overview": _clean_text(raw.get("overview"), 1200),
        "key_points": _str_list(raw.get("key_points")),
        "decisions": [],
        "action_items": [],
        "open_questions": _str_list(raw.get("open_questions")),
        "suggested_memory_updates": [],
    }

    if isinstance(raw.get("decisions"), list):
        for item in raw["decisions"][:12]:
            if isinstance(item, str):
                item = {"decision": item}
            if not isinstance(item, dict):
                continue
            decision = _clean_text(item.get("decision"), 400)
            if not decision:
                continue
            status = str(item.get("status", "")).strip().lower()
            if status not in _DECISION_STATUSES:
                status = "unclear"
            summary["decisions"].append(
                {"decision": decision, "status": status})

    if isinstance(raw.get("action_items"), list):
        for item in raw["action_items"][:12]:
            if isinstance(item, str):
                item = {"task": item}
            if not isinstance(item, dict):
                continue
            task = _clean_text(item.get("task"), 400)
            if not task:
                continue
            owner = _clean_text(item.get("owner"), 80) or "Unassigned"
            due = _clean_text(item.get("due_date"), 80) or "Not specified"
            summary["action_items"].append(
                {"task": task, "owner": owner, "due_date": due,
                 "status": "open"})

    if isinstance(raw.get("suggested_memory_updates"), list):
        for item in raw["suggested_memory_updates"][:10]:
            if not isinstance(item, dict):
                continue
            text = _clean_text(item.get("text"), 400)
            if not text:
                continue
            category = str(item.get("category", "")).strip().lower()
            if category not in _CATEGORIES:
                category = "other"
            confidence = str(item.get("confidence", "")).strip().lower()
            if confidence not in _CONFIDENCES:
                confidence = "low"
            summary["suggested_memory_updates"].append({
                "category": category,
                "text": text,
                "reason": _clean_text(item.get("reason"), 300),
                "confidence": confidence,
            })

    return summary


def generate_session_summary(transcript, mode_id):
    """Generate a normalized structured summary via local Ollama.

    Raises SummaryError when generation or parsing fails - the caller
    keeps the transcript and may retry.
    """
    if not isinstance(transcript, str) or not transcript.strip():
        raise SummaryError("Cannot summarize an empty transcript.")

    prompt = _build_prompt(transcript, mode_id)

    # LOCAL ONLY: direct Ollama call - the Groq/cloud toggle is never
    # consulted, and think:false is applied for qwen3-family models.
    result = _call_ollama(
        prompt,
        max_tokens=_SUMMARY_MAX_TOKENS,
        temperature=0.2,
        model=OLLAMA_MODEL_SUGGEST,
        num_ctx=OLLAMA_NUM_CTX_SUGGEST,
        format_json=True,
    )
    if not result:
        raise SummaryError(
            "The local model is not available or timed out. The "
            "transcript is saved - you can retry from Session History."
        )

    return _normalize(_parse_model_json(result))
