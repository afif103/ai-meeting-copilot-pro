"""
Static, synthetic question bank for the Interview Trainer (Packet 8A).

Pure data + pure selection helpers. NO filesystem, profile, LLM, network,
or mutable global navigation state - the Trainer window owns the current
index. Everything returned is immutable (frozen dataclasses inside
tuples), so callers can never mutate the shared bank.

Two tracks x three difficulties x four questions = 24 generic, synthetic,
professional questions containing no personal information.

Stdlib only.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    id: str
    name: str


@dataclass(frozen=True)
class Difficulty:
    id: str
    name: str


@dataclass(frozen=True)
class Question:
    id: str
    track: str
    difficulty: str
    normal: str          # standard wording
    simple: str          # simple-English wording (same meaning)


# Canonical ids and display names, in deterministic display order.
TRACKS = (
    Track("call_center", "Call Center"),
    Track("virtual_assistant", "Virtual Assistant"),
)
DIFFICULTIES = (
    Difficulty("easy", "Easy"),
    Difficulty("medium", "Medium"),
    Difficulty("hard", "Hard"),
)

_TRACK_IDS = frozenset(t.id for t in TRACKS)
_DIFFICULTY_IDS = frozenset(d.id for d in DIFFICULTIES)

# Exactly four questions per (track, difficulty). Order is the display
# order used by Previous/Next navigation. All content is fictional and
# free of any personal information.
_QUESTIONS = (
    # ----- Call Center / Easy -----
    Question("cc_easy_1", "call_center", "easy",
             "To start, please introduce yourself and tell me a little "
             "about your background.",
             "Can you tell me about yourself and your background?"),
    Question("cc_easy_2", "call_center", "easy",
             "What attracts you to a career in customer service?",
             "Why do you want to work in customer service?"),
    Question("cc_easy_3", "call_center", "easy",
             "In your view, what does excellent customer service look like?",
             "What does good customer service mean to you?"),
    Question("cc_easy_4", "call_center", "easy",
             "What personal strengths would you bring to a customer "
             "support role?",
             "What are your strengths for a customer support job?"),
    # ----- Call Center / Medium -----
    Question("cc_medium_1", "call_center", "medium",
             "How would you handle a customer who is angry and raising "
             "their voice?",
             "What would you do if a customer is angry and shouting?"),
    Question("cc_medium_2", "call_center", "medium",
             "A customer calls because their order arrived later than "
             "promised. How do you respond?",
             "A customer's order came late. How do you help them?"),
    Question("cc_medium_3", "call_center", "medium",
             "What steps do you take when a customer cannot clearly "
             "explain their problem?",
             "What do you do if a customer cannot explain the problem "
             "clearly?"),
    Question("cc_medium_4", "call_center", "medium",
             "How do you balance answering quickly with making sure your "
             "answer is correct?",
             "How do you stay both fast and correct when helping "
             "customers?"),
    # ----- Call Center / Hard -----
    Question("cc_hard_1", "call_center", "hard",
             "A customer demands a solution that company policy does not "
             "allow. How do you handle it?",
             "A customer wants something the rules do not allow. What do "
             "you do?"),
    Question("cc_hard_2", "call_center", "hard",
             "A customer has called several times about the same "
             "unresolved issue. How do you proceed?",
             "A customer called many times about the same problem. What "
             "do you do now?"),
    Question("cc_hard_3", "call_center", "hard",
             "Several customers are waiting at once and all seem urgent. "
             "How do you manage the queue?",
             "Many customers are waiting and all seem urgent. How do you "
             "handle this?"),
    Question("cc_hard_4", "call_center", "hard",
             "You realize you gave a customer the wrong information "
             "earlier. What do you do?",
             "You gave a customer wrong information. How do you fix it?"),
    # ----- Virtual Assistant / Easy -----
    Question("va_easy_1", "virtual_assistant", "easy",
             "Please introduce yourself and describe the kind of support "
             "work you enjoy.",
             "Tell me about yourself and the support work you like."),
    Question("va_easy_2", "virtual_assistant", "easy",
             "What draws you to working as a virtual assistant?",
             "Why do you want to be a virtual assistant?"),
    Question("va_easy_3", "virtual_assistant", "easy",
             "How do you keep your tasks and schedule organized during a "
             "busy day?",
             "How do you stay organized when the day is busy?"),
    Question("va_easy_4", "virtual_assistant", "easy",
             "What makes you an effective communicator over email and "
             "chat?",
             "What makes you good at email and chat communication?"),
    # ----- Virtual Assistant / Medium -----
    Question("va_medium_1", "virtual_assistant", "medium",
             "You have two tasks due at the same time. How do you decide "
             "what to do first?",
             "Two tasks are due at the same time. How do you choose what "
             "to do first?"),
    Question("va_medium_2", "virtual_assistant", "medium",
             "A client sends instructions you do not fully understand. "
             "What do you do next?",
             "A client's instructions are not clear. What do you do?"),
    Question("va_medium_3", "virtual_assistant", "medium",
             "A client asks you to use a software tool you have never "
             "used. How do you approach it?",
             "A client wants you to use a new tool you do not know. How "
             "do you learn it?"),
    Question("va_medium_4", "virtual_assistant", "medium",
             "How do you keep a remote client informed about the progress "
             "of their work?",
             "How do you keep a remote client updated on your work?"),
    # ----- Virtual Assistant / Hard -----
    Question("va_hard_1", "virtual_assistant", "hard",
             "You handle a client's private and confidential information. "
             "How do you keep it secure?",
             "You work with a client's private information. How do you "
             "keep it safe?"),
    Question("va_hard_2", "virtual_assistant", "hard",
             "You realize you will miss an important deadline. How do you "
             "handle the situation?",
             "You know you will miss a deadline. What do you do?"),
    Question("va_hard_3", "virtual_assistant", "hard",
             "Two clients each insist their work is the top priority. How "
             "do you manage this?",
             "Two clients both say their work is most important. What do "
             "you do?"),
    Question("va_hard_4", "virtual_assistant", "hard",
             "You notice the same small error keeps happening in a routine "
             "task. How do you prevent it?",
             "The same small mistake keeps happening in a task. How do "
             "you stop it?"),
)

# Pre-index (track, difficulty) -> immutable tuple of questions.
_BY_COMBO = {}
for _q in _QUESTIONS:
    _BY_COMBO.setdefault((_q.track, _q.difficulty), []).append(_q)
_BY_COMBO = {k: tuple(v) for k, v in _BY_COMBO.items()}

QUESTIONS_PER_COMBO = 4


def get_tracks():
    """All tracks in display order (immutable)."""
    return TRACKS


def get_difficulties():
    """All difficulties in display order (immutable)."""
    return DIFFICULTIES


def get_questions(track_id, difficulty_id):
    """The four questions for a track/difficulty, in display order.

    Returns an immutable tuple of frozen Question records. Unknown track
    or difficulty ids raise ValueError (fail closed)."""
    if track_id not in _TRACK_IDS:
        raise ValueError(f"Unknown track: {track_id!r}")
    if difficulty_id not in _DIFFICULTY_IDS:
        raise ValueError(f"Unknown difficulty: {difficulty_id!r}")
    return _BY_COMBO[(track_id, difficulty_id)]


def get_question_text(question, simple_english):
    """The wording to display for a question - simple-English when the
    toggle is on, otherwise the standard wording."""
    return question.simple if simple_english else question.normal
