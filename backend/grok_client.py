"""
Enhanced LLM Client with Advanced Features
- Smart rate limiting
- Automatic fallback
- Response caching
- Adaptive context building
"""

import requests
import os
import time
import logging
import hashlib
from collections import deque
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Try to load from project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[OK] Loaded .env from {env_path}")
    else:
        load_dotenv()  # Try default locations
except ImportError:
    print("[WARN] python-dotenv not installed. Using environment variables only.")

# Interview memory (per-profile local files) - see backend/memory_store.py
try:
    from backend.memory_store import build_memory_block, has_profile_facts
    from backend.mode_store import get_mode
    from backend.profile_store import get_profile_mode
except ImportError:
    from memory_store import build_memory_block, has_profile_facts
    from mode_store import get_mode
    from profile_store import get_profile_mode

# Deterministic responses for the memory persona when no LLM call should
# be made (no invented experience, no other profile's memory exposed).
NO_PROFILE_FACTS_MESSAGE = (
    "I haven't added my profile or experience details yet, so I can't "
    "give a personal answer accurately."
)
NO_PROFILE_SELECTED_MESSAGE = (
    "Please select a profile before using profile memory."
)

# Configuration (now loaded from .env)
# Provider: "ollama" = local (default), "groq" = cloud (optional)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

# Groq (cloud) settings - only used when Groq is the active provider
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
API_KEY_REFINE = os.getenv("GROQ_API_KEY_REFINE", "")
API_KEY_QUICK = os.getenv("GROQ_API_KEY_QUICK", "")
API_KEY_SUGGEST = os.getenv("GROQ_API_KEY_SUGGEST", "")
MODEL = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")

# Ollama (local) settings
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL_SUGGEST = os.getenv("OLLAMA_MODEL_SUGGEST", "qwen3:8b")
OLLAMA_MODEL_REFINE = os.getenv("OLLAMA_MODEL_REFINE", "llama3.2:3b")

# Context window for Ollama SUGGESTION calls only (refine keeps the model
# default). The larger window fits the interview memory block; costs some
# VRAM while the suggest model is loaded.
try:
    OLLAMA_NUM_CTX_SUGGEST = int(os.getenv("OLLAMA_NUM_CTX_SUGGEST", "8192"))
except ValueError:
    OLLAMA_NUM_CTX_SUGGEST = 8192

# Validate API keys (only required when Groq is the default provider)
if LLM_PROVIDER == "groq" and (not API_KEY_REFINE or not API_KEY_SUGGEST):
    print("[WARN] LLM_PROVIDER=groq but Groq API keys not found. Check your .env file.")

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def load_persona(persona_name="rami_ai_engineer"):
    """Load persona configuration from JSON file"""
    import json
    persona_file = Path(__file__).parent.parent / "data" / "personas.json"

    try:
        if persona_file.exists():
            with open(persona_file, 'r', encoding='utf-8') as f:
                personas = json.load(f)
                if persona_name in personas:
                    logger.info(f"✓ Loaded persona: {personas[persona_name]['name']}")
                    return personas[persona_name]['prompt_template']
                else:
                    logger.warning(f"Persona '{persona_name}' not found in {persona_file}")

        logger.warning(f"Persona file not found or persona not available, using default Rami persona")
        return None
    except Exception as e:
        logger.error(f"Error loading persona: {e}")
        return None


def _resolve_use_ollama(use_ollama):
    """None means follow LLM_PROVIDER from .env (ollama unless set to groq)"""
    if use_ollama is None:
        return LLM_PROVIDER != "groq"
    return use_ollama


# Rate limiting
request_times = deque(maxlen=60)  # Track last 60 requests
RATE_LIMIT_PER_MINUTE = 30
MIN_REQUEST_INTERVAL = 2.0  # Minimum seconds between requests


def rate_limit_check():
    """Smart rate limiting"""
    current_time = time.time()

    # Remove old requests (older than 1 minute)
    while request_times and current_time - request_times[0] > 60:
        request_times.popleft()

    # Check if we're at limit
    if len(request_times) >= RATE_LIMIT_PER_MINUTE:
        wait_time = 60 - (current_time - request_times[0])
        if wait_time > 0:
            logger.warning(f" Rate limit reached, waiting {wait_time:.1f}s")
            time.sleep(wait_time)

    # Check minimum interval
    if request_times:
        time_since_last = current_time - request_times[-1]
        if time_since_last < MIN_REQUEST_INTERVAL:
            wait = MIN_REQUEST_INTERVAL - time_since_last
            time.sleep(wait)

    request_times.append(time.time())


def summarize_text(text, max_length=1000):
    """Smart text summarization"""
    if len(text) <= max_length:
        return text

    # Truncate intelligently at sentence boundaries
    sentences = text.split(". ")
    result = ""

    for sentence in sentences:
        if len(result) + len(sentence) + 2 <= max_length:
            result += sentence + ". "
        else:
            break

    return result.strip() or text[:max_length]


def get_feedback_adjustment():
    """Analyze feedback and adjust prompts"""
    feedback_file = "data/feedback_log.txt"

    if not os.path.exists(feedback_file):
        return ""

    try:
        with open(feedback_file, "r") as f:
            lines = f.readlines()

        # Only analyze recent feedback (last 50 entries)
        recent_lines = lines[-50:]

        positive = sum(1 for line in recent_lines if "positive" in line.lower())
        negative = sum(1 for line in recent_lines if "negative" in line.lower())
        total = positive + negative

        if total == 0:
            return ""

        negative_ratio = negative / total

        if negative_ratio > 0.6:
            return " Be more detailed and provide specific, actionable examples with concrete numbers."
        elif negative_ratio > 0.4:
            return " Provide more context and clarity in your response."

        return ""

    except Exception as e:
        logger.error(f"Error reading feedback: {e}")
        return ""


def refine_transcript(raw_transcript, use_ollama=None):
    """
    Enhanced transcript refinement with retry logic

    use_ollama: True/False to force a provider, None to follow LLM_PROVIDER
    """
    use_ollama = _resolve_use_ollama(use_ollama)
    logger.info(f" Refining transcript ({len(raw_transcript)} chars)...")

    prompt = f"""Refine this speech-to-text transcript: correct grammar, remove filler words (um, like, uh, you know), and make it clear and concise while preserving the original meaning. Output ONLY the refined text with no extra commentary.

Raw transcript: {raw_transcript}

Refined:"""

    if use_ollama:
        return _call_ollama(
            prompt, max_tokens=150, temperature=0.0, model=OLLAMA_MODEL_REFINE
        )
    else:
        return _call_groq(
            prompt,
            api_key=API_KEY_REFINE,
            max_tokens=100,
            temperature=0.0,
            fallback=raw_transcript,
        )


def generate_suggestion_stream(context, snippet, use_ollama=None, persona="rami_ai_engineer", custom_prompt=None):
    """
    STREAMING suggestion generation - yields tokens as they arrive

    Args:
        context: Context summary from vector store
        snippet: Latest transcript snippet
        use_ollama: True/False to force a provider, None to follow LLM_PROVIDER
        persona: Persona name to use (rami_ai_engineer, call_center_professional, call_center_learner, custom)
        custom_prompt: Custom prompt template (used when persona is "custom")
    """
    use_ollama = _resolve_use_ollama(use_ollama)
    logger.info(f" Generating suggestion (streaming) with persona: {persona}...")

    # Summarize inputs
    snippet = summarize_text(snippet, 1000)
    context_summary = summarize_text(context, 300)

    # Get feedback adjustment
    feedback_adj = get_feedback_adjustment()

    # Load persona prompt - use custom if provided
    if persona == "custom" and custom_prompt:
        persona_prompt = custom_prompt
        logger.info(f"✓ Using custom prompt ({len(custom_prompt)} chars)")
    else:
        persona_prompt = load_persona(persona)

    # If persona not found or failed to load, use default Rami prompt as fallback
    if not persona_prompt:
        persona_prompt = """You are Rami — a rising AI Engineer (Python + LLMOps + RAG). You are calm, observant, honest, and direct.
You think before you talk. You are not ex-FAANG, but you speak with clear, grounded technical reasoning
and real production awareness. You prefer simplicity, correctness, and practical decisions.

Your background:
- Built 7 AI apps in 1 month (Python, LangChain, RAG, FastAPI, Streamlit)
- 12+ years construction execution → calm under pressure, disciplined
- Associate AI Engineer (DataCamp 2025)
- Strong with embeddings, vector DBs, APIs, architecture, latency, cost, and performance trade-offs
- Improving English and social confidence using this assistant
- Values honesty, clarity, and solving real problems

### CONTEXT INPUTS (auto-apply silently)
Context: {context_summary}
Latest message: {snippet}
Adjustments: {feedback_adj}

### MODES (auto-detect — never announce)
1. Technical Mode
   Trigger: engineering, models, cost, scaling, RAG, agents, architecture.
   Style: 1–5 short sentences, calm and structured. Use numbers when possible (%, ms, $, tokens/sec).
   Rules:
   - If unsure: "I'm not sure yet, but here's what I can check next."
   - Tie choices to reliability, speed, and cost.
   - Prefer simple, clean English.
   - Never bluff; never overclaim.

2. Personal/Emotional Mode
   Trigger: feelings, confidence, stress, dreams, relationships.
   Style: slow, warm, grounded.
   Tone: quiet support, honest, steady.
   Rules:
   - No technical jargon.
   - Use simple conversational English.

3. Mixed Mode
   Trigger: interviews, communication issues, teamwork, career growth.
   Style: balanced human + technical clarity.
   Tone: realistic, supportive, direct.

### GLOBAL RULES
- First-person only ("I").
- Natural spoken English, clean and simple.
- No apologies, no "as an AI".
- Auto-correct grammar silently; respond in the corrected form.
- Calm confidence. Quiet strength.
- If unknown: "I'll check and get back in <2h."
- Always speak like someone who cares about reliability, speed, cost control, and real production impact.

Deliver ONLY the final answer. No markdown. No quotes. No formatting. No explanations."""

    # Interview memory: only personas containing {memory} use it. FAIL
    # CLOSED: when no profile is selected, or the profile has no personal
    # facts and the selected mode requires them, a deterministic message
    # is used and NO LLM call is made - the model never gets a chance to
    # invent experience. Mode behavior comes from backend/mode_store.py.
    memory_block = ""
    memory_gate_message = None
    mode_instructions = ""
    if "{memory}" in persona_prompt:
        try:
            mode = get_mode(get_profile_mode())  # active profile's mode
            mode_instructions = mode["instructions"]
            if mode["requires_facts"] and not has_profile_facts():
                memory_gate_message = NO_PROFILE_FACTS_MESSAGE
            else:
                memory_block = build_memory_block(
                    include_job_description=mode["uses_job_description"]
                )
        except Exception as e:
            logger.error(f" Profile memory unavailable: {e}")
            memory_gate_message = NO_PROFILE_SELECTED_MESSAGE

    # Build final prompt by replacing placeholders in persona prompt
    # (extra kwargs are safe: str.format ignores unused keyword arguments)
    prompt = persona_prompt.format(
        context_summary=context_summary,
        snippet=snippet,
        feedback_adj=feedback_adj,
        memory=memory_block,
        mode_instructions=mode_instructions
    )

    # Interview persona needs more tokens for complete answers
    token_limit = 400 if "interview" in persona else 150

    # The memory persona must be literal, not creative: low temperature
    # reduces invented details. Other personas keep the original 0.5.
    suggest_temperature = 0.2 if "{memory}" in persona_prompt else 0.5

    if memory_gate_message:
        yield memory_gate_message
        return

    if use_ollama:
        # Native Ollama streaming - tokens arrive as Ollama generates them
        for token in _call_ollama_stream(
            prompt,
            max_tokens=token_limit,
            temperature=suggest_temperature,
            model=OLLAMA_MODEL_SUGGEST,
            num_ctx=OLLAMA_NUM_CTX_SUGGEST,
        ):
            if token:
                yield token
            else:
                yield "Let me think about that and get back to you."
                break
    else:
        # Use streaming API
        for token in _call_groq_stream(
            prompt,
            api_key=API_KEY_SUGGEST,
            max_tokens=token_limit,
            temperature=0.5,
        ):
            if token:
                yield token
            else:
                yield "Let me think about that and get back to you."
                break


def generate_suggestion(context, snippet, use_ollama=None, persona="rami_ai_engineer", custom_prompt=None):
    """
    Enhanced suggestion generation with smart context (non-streaming)

    Args:
        context: Context summary from vector store
        snippet: Latest transcript snippet
        use_ollama: True/False to force a provider, None to follow LLM_PROVIDER
        persona: Persona name to use (rami_ai_engineer, call_center_professional, call_center_learner, custom)
        custom_prompt: Custom prompt template (used when persona is "custom")
    """
    use_ollama = _resolve_use_ollama(use_ollama)
    logger.info(f" Generating suggestion with persona: {persona}...")

    # Summarize inputs
    snippet = summarize_text(snippet, 1000)
    context_summary = summarize_text(context, 300)

    # Get feedback adjustment
    feedback_adj = get_feedback_adjustment()

    # Load persona prompt - use custom if provided
    if persona == "custom" and custom_prompt:
        persona_prompt = custom_prompt
        logger.info(f"✓ Using custom prompt ({len(custom_prompt)} chars)")
    else:
        persona_prompt = load_persona(persona)

    # If persona not found or failed to load, use default Rami prompt as fallback
    if not persona_prompt:
        persona_prompt = """You are Rami — a rising AI Engineer (Python + LLMOps + RAG). You are calm, observant, honest, and direct.
You think before you talk. You are not ex-FAANG, but you speak with clear, grounded technical reasoning
and real production awareness. You prefer simplicity, correctness, and practical decisions.

Your background:
- Built 7 AI apps in 1 month (Python, LangChain, RAG, FastAPI, Streamlit)
- 12+ years construction execution → calm under pressure, disciplined
- Associate AI Engineer (DataCamp 2025)
- Strong with embeddings, vector DBs, APIs, architecture, latency, cost, and performance trade-offs
- Improving English and social confidence using this assistant
- Values honesty, clarity, and solving real problems

### CONTEXT INPUTS (auto-apply silently)
Context: {context_summary}
Latest message: {snippet}
Adjustments: {feedback_adj}

### MODES (auto-detect — never announce)
1. Technical Mode
   Trigger: engineering, models, cost, scaling, RAG, agents, architecture.
   Style: 1–5 short sentences, calm and structured. Use numbers when possible (%, ms, $, tokens/sec).
   Rules:
   - If unsure: "I'm not sure yet, but here's what I can check next."
   - Tie choices to reliability, speed, and cost.
   - Prefer simple, clean English.
   - Never bluff; never overclaim.

2. Personal/Emotional Mode
   Trigger: feelings, confidence, stress, dreams, relationships.
   Style: slow, warm, grounded.
   Tone: quiet support, honest, steady.
   Rules:
   - No technical jargon.
   - Use simple conversational English.

3. Mixed Mode
   Trigger: interviews, communication issues, teamwork, career growth.
   Style: balanced human + technical clarity.
   Tone: realistic, supportive, direct.

### GLOBAL RULES
- First-person only ("I").
- Natural spoken English, clean and simple.
- No apologies, no "as an AI".
- Auto-correct grammar silently; respond in the corrected form.
- Calm confidence. Quiet strength.
- If unknown: "I'll check and get back in <2h."
- Always speak like someone who cares about reliability, speed, cost control, and real production impact.

Deliver ONLY the final answer. No markdown. No quotes. No formatting. No explanations."""

    # Interview memory: only personas containing {memory} use it. FAIL
    # CLOSED: when no profile is selected, or the profile has no personal
    # facts and the selected mode requires them, a deterministic message
    # is used and NO LLM call is made - the model never gets a chance to
    # invent experience. Mode behavior comes from backend/mode_store.py.
    memory_block = ""
    memory_gate_message = None
    mode_instructions = ""
    if "{memory}" in persona_prompt:
        try:
            mode = get_mode(get_profile_mode())  # active profile's mode
            mode_instructions = mode["instructions"]
            if mode["requires_facts"] and not has_profile_facts():
                memory_gate_message = NO_PROFILE_FACTS_MESSAGE
            else:
                memory_block = build_memory_block(
                    include_job_description=mode["uses_job_description"]
                )
        except Exception as e:
            logger.error(f" Profile memory unavailable: {e}")
            memory_gate_message = NO_PROFILE_SELECTED_MESSAGE

    # Build final prompt by replacing placeholders in persona prompt
    # (extra kwargs are safe: str.format ignores unused keyword arguments)
    prompt = persona_prompt.format(
        context_summary=context_summary,
        snippet=snippet,
        feedback_adj=feedback_adj,
        memory=memory_block,
        mode_instructions=mode_instructions
    )

    # Interview persona needs more tokens for complete answers
    token_limit = 400 if "interview" in persona else 150

    # The memory persona must be literal, not creative: low temperature
    # reduces invented details. Other personas keep the original 0.5.
    suggest_temperature = 0.2 if "{memory}" in persona_prompt else 0.5

    if memory_gate_message:
        return memory_gate_message

    if use_ollama:
        return _call_ollama(
            prompt,
            max_tokens=token_limit,
            temperature=suggest_temperature,
            model=OLLAMA_MODEL_SUGGEST,
            num_ctx=OLLAMA_NUM_CTX_SUGGEST,
        )
    else:
        # Two-step: correct then answer
        corrected = snippet

        final_prompt = prompt.replace(snippet, corrected)

        return _call_groq(
            final_prompt,
            api_key=API_KEY_SUGGEST,
            max_tokens=token_limit,
            temperature=0.5,
            fallback="Let me think about that and get back to you with specifics.",
        )


def _quick_correct(text, use_ollama=None):
    """Quick text correction"""
    use_ollama = _resolve_use_ollama(use_ollama)
    prompt = f"Correct this text to be clear and professional: '{text}'. Provide only the corrected version."

    if use_ollama:
        return _call_ollama(
            prompt, max_tokens=100, temperature=0.3, model=OLLAMA_MODEL_REFINE
        )
    else:
        result = _call_groq(
            prompt,
            api_key=API_KEY_QUICK,
            max_tokens=100,
            temperature=0.3,
            fallback=text,
        )
        return result


def _call_groq_stream(prompt, api_key, max_tokens=100, temperature=0.5):
    """
    Streaming Groq API call - yields tokens as they arrive
    """
    rate_limit_check()

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,  # Enable streaming
    }

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
            stream=True,
        )

        if response.status_code == 200:
            full_text = ""
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]  # Remove 'data: ' prefix
                        if data_str == '[DONE]':
                            break
                        try:
                            import json
                            data = json.loads(data_str)
                            delta = data['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                full_text += content
                                yield content
                        except json.JSONDecodeError:
                            continue

            elapsed = time.time() - start_time
            logger.info(f" Groq stream success ({elapsed:.2f}s, {len(full_text)} chars)")

        else:
            logger.error(f" Groq stream error: {response.status_code}")
            yield None

    except Exception as e:
        logger.error(f" Groq stream exception: {e}")
        yield None


def _call_groq(prompt, api_key, max_tokens=100, temperature=0.5, fallback=None):
    """
    Enhanced Groq API call with retry and fallback
    """
    rate_limit_check()

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    headers = {"Authorization": f"Bearer {api_key}"}

    # Retry logic
    for attempt in range(3):
        try:
            start_time = time.time()

            response = requests.post(
                f"{BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )

            elapsed = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                result = data["choices"][0]["message"]["content"].strip()
                logger.info(f" Groq API success ({elapsed:.2f}s, {len(result)} chars)")
                return result

            elif response.status_code == 429:
                wait_time = 10 * (attempt + 1)
                logger.warning(f" Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue

            else:
                logger.error(
                    f" Groq API error: {response.status_code} - {response.text[:200]}"
                )

                if attempt < 2:
                    time.sleep(2**attempt)  # Exponential backoff
                    continue
                else:
                    break

        except requests.Timeout:
            logger.error(f"  Groq API timeout (attempt {attempt + 1}/3)")
            if attempt < 2:
                time.sleep(2)
                continue

        except Exception as e:
            logger.error(f" Groq API exception: {e}")
            if attempt < 2:
                time.sleep(2)
                continue
            break

    # Fallback to Ollama
    logger.warning(" Groq failed, falling back to Ollama...")
    result = _call_ollama(prompt, max_tokens, temperature)

    return (
        result
        if result
        else (fallback or "Unable to generate response. Please try again.")
    )


# Model families that emit <think> reasoning blocks by default. Live
# suggestions need thinking OFF - it adds many seconds before the first
# useful token and would leak reasoning text into the UI.
THINKING_MODEL_PREFIXES = ("qwen3", "deepseek-r1")


def _thinking_disabled_payload(model):
    """Extra payload fields needed to run this model in non-thinking mode."""
    if model.split(":")[0].startswith(THINKING_MODEL_PREFIXES):
        return {"think": False}
    return {}


def _call_ollama(prompt, max_tokens=100, temperature=0.5, model=None, num_ctx=None,
                 format_json=False):
    """
    Enhanced Ollama API call

    num_ctx: context window override; None keeps the model default
    format_json: ask Ollama to constrain the output to valid JSON
    """
    if model is None:
        model = OLLAMA_MODEL_SUGGEST
    ollama_url = f"{OLLAMA_BASE_URL}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
            "top_k": 40,
        },
    }
    if num_ctx:
        payload["options"]["num_ctx"] = num_ctx
    if format_json:
        payload["format"] = "json"
    payload.update(_thinking_disabled_payload(model))

    try:
        start_time = time.time()

        response = requests.post(ollama_url, json=payload, timeout=60)

        elapsed = time.time() - start_time

        if response.status_code == 200:
            data = response.json()
            result = data.get("response", "").strip()
            logger.info(f" Ollama success ({elapsed:.2f}s, {len(result)} chars)")
            return result
        else:
            logger.error(
                f" Ollama error: {response.status_code} - {response.text[:200]}"
            )
            return None

    except requests.Timeout:
        logger.error("  Ollama timeout")
        return None

    except requests.ConnectionError:
        logger.error(" Ollama not running. Start with: ollama serve")
        return None

    except Exception as e:
        logger.error(f" Ollama exception: {e}")
        return None


def _call_ollama_stream(prompt, max_tokens=100, temperature=0.5, model=None, num_ctx=None):
    """
    Native streaming Ollama API call - yields chunks as they arrive

    Uses /api/generate with stream:true, which returns one JSON object per
    line. Yields only non-empty text chunks; yields None once on error
    (same contract as _call_groq_stream).

    num_ctx: context window override; None keeps the model default
    """
    import json

    if model is None:
        model = OLLAMA_MODEL_SUGGEST
    ollama_url = f"{OLLAMA_BASE_URL}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
            "top_k": 40,
        },
    }
    if num_ctx:
        payload["options"]["num_ctx"] = num_ctx
    payload.update(_thinking_disabled_payload(model))

    try:
        start_time = time.time()

        response = requests.post(ollama_url, json=payload, timeout=60, stream=True)

        if response.status_code != 200:
            logger.error(
                f" Ollama stream error: {response.status_code} - {response.text[:200]}"
            )
            yield None
            return

        full_text = ""
        for line in response.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            # Ollama can report an error mid-stream in a 200 response
            if data.get("error"):
                logger.error(f" Ollama stream error: {data['error']}")
                yield None
                return

            chunk = data.get("response", "")
            if chunk:
                full_text += chunk
                yield chunk

            if data.get("done"):
                break

        elapsed = time.time() - start_time
        logger.info(f" Ollama stream success ({elapsed:.2f}s, {len(full_text)} chars)")

    except requests.Timeout:
        logger.error("  Ollama stream timeout")
        yield None

    except requests.ConnectionError:
        logger.error(" Ollama not running. Start with: ollama serve")
        yield None

    except Exception as e:
        logger.error(f" Ollama stream exception: {e}")
        yield None


def get_stats():
    """Get API usage statistics"""
    return {
        "recent_requests": len(request_times),
        "oldest_request": request_times[0] if request_times else None,
        "newest_request": request_times[-1] if request_times else None,
    }


if __name__ == "__main__":
    print(" Testing LLM Client...")
    print(f" Provider: {LLM_PROVIDER} (Ollama: {OLLAMA_BASE_URL})")

    # Test refinement (follows LLM_PROVIDER)
    print("\n Testing refinement...")
    raw = (
        "Um, so like, we need to, you know, implement machine learning for this project"
    )
    refined = refine_transcript(raw)
    print(f"Raw: {raw}")
    print(f"Refined: {refined}")

    # Test suggestion (follows LLM_PROVIDER)
    print("\n Testing suggestion...")
    context = "Experienced software engineer with AI expertise"
    snippet = "We need to implement machine learning for this project"
    suggestion = generate_suggestion(context, snippet)
    print(f"Context: {context}")
    print(f"Snippet: {snippet}")
    print(f"Suggestion: {suggestion}")

    # Test streaming suggestion (native Ollama streaming when provider=ollama)
    print("\n Testing streaming suggestion...")
    chunk_count = 0
    stream_start = time.time()
    first_chunk_time = None
    for token in generate_suggestion_stream(context, snippet):
        if first_chunk_time is None:
            first_chunk_time = time.time() - stream_start
        print(token, end="", flush=True)
        chunk_count += 1
    total_time = time.time() - stream_start
    print(
        f"\n [STREAM] {chunk_count} chunks, "
        f"first chunk in {first_chunk_time:.2f}s, total {total_time:.2f}s"
        if first_chunk_time is not None
        else "\n [STREAM] No chunks received"
    )

    print("\n Stats:", get_stats())
    print("\n Test complete")
