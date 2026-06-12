"""
Benchmark local Ollama models for AI Meeting Copilot Pro.

Measures what matters for live interview/meeting suggestions:
- time to first token (how fast text starts appearing)
- total response time and tokens/sec
- chunk count and streaming smoothness (max gap between chunks)
- VRAM/RAM footprint while loaded (via /api/ps)
- cold-load time (first use in a session)

Sample answers are printed and saved so a human can judge quality.

Usage:
    python tools/benchmark_ollama_models.py                  # default candidates
    python tools/benchmark_ollama_models.py llama3.2:3b      # specific model(s)
    python tools/benchmark_ollama_models.py qwen3:4b --pull  # pull if missing

Models are NEVER downloaded unless --pull is given. Heavy models
(qwen3:14b, qwen3:30b-a3b) are never pulled by this script - pull those
manually with `ollama pull <model>` if you decide to test them.

Results are saved to data/benchmark_results.json (gitignored).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Load .env from project root (script lives in tools/)
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
    else:
        load_dotenv()
except ImportError:
    pass

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

# Candidates benchmarked when no models are passed on the command line.
# Missing ones are skipped (or pulled with --pull).
DEFAULT_CANDIDATES = [
    "llama3.2:3b",  # current refine model (baseline)
    "qwen2.5-coder:7b",  # current suggest model (baseline)
    "qwen3:4b",
    "qwen3:8b",
    "gemma3:4b",
]

# Never pulled by this script, even with --pull (too big to download
# casually; qwen3:30b-a3b is ~18 GB). Pull manually if you want them.
HEAVY_MODELS = {"qwen3:14b", "qwen3:30b-a3b", "qwen3:30b"}

# Model families that emit <think> reasoning blocks by default. For live
# suggestions thinking must be OFF (it adds many seconds before the first
# useful token), so we benchmark these with think disabled - same as the
# app would need to run them.
THINKING_MODEL_PREFIXES = ("qwen3", "deepseek-r1")


def thinking_disabled_payload(model):
    """Extra payload fields needed to run this model in non-thinking mode."""
    base = model.split(":")[0]
    if base.startswith(THINKING_MODEL_PREFIXES):
        return {"think": False}
    return {}

# Prompts mirror how the app actually uses the LLM (see backend/grok_client.py):
# interview-style suggestions get up to 400 tokens, refine/short tasks 150.
PROMPTS = [
    {
        "name": "interview_short",
        "max_tokens": 400,
        "prompt": (
            "You are Rami answering a job interview question. You are an AI "
            "engineer who built a full-stack AI platform (Next.js, FastAPI, "
            "PostgreSQL, Redis, ChromaDB, deployed on AWS for $11/month) and "
            "a 4-agent RAG platform with 35+ tests. Answer in first person, "
            "3-5 natural spoken sentences, first sentence answers directly, "
            "no markdown.\n\nInterview question: Tell me about yourself and "
            "what you have built."
        ),
    },
    {
        "name": "technical_explanation",
        "max_tokens": 400,
        "prompt": (
            "You are Rami in a technical interview. Explain in first person, "
            "4-6 spoken sentences, no markdown: how does a RAG pipeline work, "
            "and what trade-offs did you consider when you chose ChromaDB "
            "over Pinecone for your project?"
        ),
    },
    {
        "name": "transcript_refine",
        "max_tokens": 150,
        "prompt": (
            "Refine this speech-to-text transcript: correct grammar, remove "
            "filler words (um, like, uh, you know), and make it clear and "
            "concise while preserving the original meaning. Output ONLY the "
            "refined text with no extra commentary.\n\nRaw transcript: Um, "
            "so like, basically what we, uh, what we wanna do is, you know, "
            "take the audio from the meeting and, like, turn it into text in "
            "real time so the, um, the AI can suggest answers.\n\nRefined:"
        ),
    },
    {
        "name": "followup_suggestion",
        "max_tokens": 150,
        "prompt": (
            "You are helping someone in a live meeting. The other person just "
            "said: 'We are worried the model will be too slow in production.' "
            "Suggest ONE short, natural follow-up response the user should "
            "say, in first person, 1-3 sentences, no markdown, no quotes."
        ),
    },
]


def api_get(path, timeout=10):
    return requests.get(f"{OLLAMA_BASE_URL}{path}", timeout=timeout)


def get_installed_models():
    """Return set of installed model names (tags) from the Ollama server."""
    resp = api_get("/api/tags")
    resp.raise_for_status()
    return {m["name"] for m in resp.json().get("models", [])}


def normalize(name):
    """Ollama treats 'llama3.2' and 'llama3.2:latest' as the same model."""
    return name if ":" in name else f"{name}:latest"


def pull_model(name):
    """Pull a model with condensed progress output."""
    print(f"  Pulling {name} (this downloads the model)...")
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/pull",
        json={"model": name},
        stream=True,
        timeout=(10, 600),
    )
    last_status = ""
    for line in resp.iter_lines():
        if not line:
            continue
        try:
            data = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("error"):
            print(f"  [ERROR] Pull failed: {data['error']}")
            return False
        status = data.get("status", "")
        total = data.get("total")
        completed = data.get("completed")
        if total and completed:
            pct = completed / total * 100
            print(f"\r  {status} {pct:5.1f}%", end="", flush=True)
        elif status != last_status:
            print(f"\n  {status}", end="", flush=True)
            last_status = status
    print("\n  Pull complete.")
    return True


def warmup(model):
    """Load the model and measure cold-load time. Returns (load_s, error)."""
    try:
        start = time.time()
        payload = {"model": model, "prompt": "Hi", "stream": False,
                   "options": {"num_predict": 1}}
        payload.update(thinking_disabled_payload(model))
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=(10, 300),
        )
        elapsed = time.time() - start
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}: {resp.text[:120]}"
        # load_duration is in nanoseconds; falls back to wall time
        load_ns = resp.json().get("load_duration")
        return (load_ns / 1e9 if load_ns else elapsed), None
    except requests.RequestException as e:
        return None, str(e)


def get_loaded_memory(model):
    """Return (total_bytes, vram_bytes) for the loaded model via /api/ps."""
    try:
        resp = api_get("/api/ps")
        for m in resp.json().get("models", []):
            if m.get("name") == model:
                return m.get("size", 0), m.get("size_vram", 0)
    except requests.RequestException:
        pass
    return 0, 0


def unload_model(model):
    """Unload the model so the next one gets full VRAM."""
    try:
        requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=(10, 60),
        )
    except requests.RequestException:
        pass


def bench_prompt(model, spec):
    """Run one streaming generation and collect timing metrics."""
    payload = {
        "model": model,
        "prompt": spec["prompt"],
        "stream": True,
        "options": {
            "num_predict": spec["max_tokens"],
            "temperature": 0.5,
            "top_p": 0.9,
            "top_k": 40,
        },
    }
    payload.update(thinking_disabled_payload(model))

    result = {
        "prompt_name": spec["name"],
        "ttft_s": None,
        "total_s": None,
        "chunks": 0,
        "chars": 0,
        "tokens": None,
        "tok_per_s": None,
        "max_gap_s": 0.0,
        "answer": "",
        "error": None,
    }

    try:
        start = time.time()
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            stream=True,
            timeout=(10, 300),
        )
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:120]}"
            return result

        last_chunk_time = start
        final = {}
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if data.get("error"):
                result["error"] = data["error"]
                return result

            chunk = data.get("response", "")
            now = time.time()
            if chunk:
                if result["ttft_s"] is None:
                    result["ttft_s"] = now - start
                else:
                    gap = now - last_chunk_time
                    if gap > result["max_gap_s"]:
                        result["max_gap_s"] = gap
                last_chunk_time = now
                result["chunks"] += 1
                result["chars"] += len(chunk)
                result["answer"] += chunk

            if data.get("done"):
                final = data
                break

        result["total_s"] = time.time() - start
        # Ollama reports eval_count/eval_duration (ns) in the final chunk
        if final.get("eval_count") and final.get("eval_duration"):
            result["tokens"] = final["eval_count"]
            result["tok_per_s"] = final["eval_count"] / (final["eval_duration"] / 1e9)
        result["answer"] = result["answer"].strip()

    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def fmt(value, suffix="", width=8, decimals=2):
    if value is None:
        return "-".rjust(width)
    return f"{value:.{decimals}f}{suffix}".rjust(width)


def gb(num_bytes):
    return f"{num_bytes / 1e9:.1f}GB" if num_bytes else "-"


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark local Ollama models for AI Meeting Copilot Pro"
    )
    parser.add_argument(
        "models",
        nargs="*",
        default=None,
        help=f"models to benchmark (default: {', '.join(DEFAULT_CANDIDATES)})",
    )
    parser.add_argument(
        "--pull",
        action="store_true",
        help="pull missing models first (heavy models are never pulled)",
    )
    parser.add_argument(
        "--output",
        default="data/benchmark_results.json",
        help="where to save results JSON (default: data/benchmark_results.json)",
    )
    args = parser.parse_args()

    candidates = [normalize(m) for m in (args.models or DEFAULT_CANDIDATES)]

    print(f"Ollama server: {OLLAMA_BASE_URL}")
    try:
        installed = get_installed_models()
    except requests.RequestException as e:
        print(f"[ERROR] Cannot reach Ollama at {OLLAMA_BASE_URL}: {e}")
        print("        Is Ollama installed and running? Try: ollama serve")
        sys.exit(1)

    # Decide which models actually get benchmarked
    to_run = []
    for model in candidates:
        if model in installed:
            to_run.append(model)
        elif args.pull and model not in HEAVY_MODELS:
            if pull_model(model):
                to_run.append(model)
        elif model in HEAVY_MODELS:
            print(f"  [SKIP] {model} - heavy model, not installed. "
                  f"Pull manually if wanted: ollama pull {model}")
        else:
            print(f"  [SKIP] {model} - not installed (use --pull to download)")

    if not to_run:
        print("\nNo installed models to benchmark.")
        sys.exit(1)

    print(f"\nBenchmarking {len(to_run)} model(s): {', '.join(to_run)}")
    print(f"{len(PROMPTS)} prompts per model, app-realistic token limits.\n")

    all_results = []
    for model in to_run:
        print(f"=== {model} ===")
        load_s, err = warmup(model)
        if err:
            print(f"  [ERROR] Could not load model: {err}\n")
            all_results.append({"model": model, "error": err, "prompts": []})
            continue
        mem_total, mem_vram = get_loaded_memory(model)
        print(f"  Loaded in {load_s:.1f}s | memory {gb(mem_total)} "
              f"(VRAM {gb(mem_vram)})")

        model_result = {
            "model": model,
            "load_s": round(load_s, 2),
            "mem_bytes": mem_total,
            "vram_bytes": mem_vram,
            "prompts": [],
        }

        for spec in PROMPTS:
            r = bench_prompt(model, spec)
            model_result["prompts"].append(r)
            if r["error"]:
                print(f"  {spec['name']:<24} ERROR: {r['error']}")
            else:
                print(
                    f"  {spec['name']:<24} ttft {r['ttft_s']:.2f}s | "
                    f"total {r['total_s']:.2f}s | {r['chunks']} chunks | "
                    f"{fmt(r['tok_per_s'], '', 6, 1).strip()} tok/s"
                )

        all_results.append(model_result)
        unload_model(model)
        print()

    # ----- Summary table -----
    header = (
        f"{'MODEL':<22}{'LOAD':>7}{'MEM':>8}{'VRAM':>8}"
        f"{'TTFT':>8}{'TOTAL':>8}{'TOK/S':>8}{'MAXGAP':>8}"
    )
    print("=" * len(header))
    print("SUMMARY (averages across prompts)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for mr in all_results:
        ok = [p for p in mr.get("prompts", []) if not p.get("error")]
        if not ok:
            print(f"{mr['model']:<22}  -- all prompts failed --")
            continue
        avg = lambda key: sum(p[key] for p in ok if p[key] is not None) / len(ok)
        print(
            f"{mr['model']:<22}"
            f"{fmt(mr.get('load_s'), 's', 7, 1)}"
            f"{gb(mr.get('mem_bytes', 0)):>8}"
            f"{gb(mr.get('vram_bytes', 0)):>8}"
            f"{fmt(avg('ttft_s'), 's', 7)}"
            f"{fmt(avg('total_s'), 's', 7)}"
            f"{fmt(avg('tok_per_s'), '', 8, 1)}"
            f"{fmt(avg('max_gap_s'), 's', 7)}"
        )
    print("=" * len(header))

    # ----- Sample answers for human quality review -----
    print("\nSAMPLE ANSWERS (truncated - full text in the results JSON)")
    for mr in all_results:
        for p in mr.get("prompts", []):
            if p.get("error"):
                continue
            answer = p["answer"].replace("\n", " ")
            if len(answer) > 220:
                answer = answer[:220] + "..."
            print(f"\n[{mr['model']} / {p['prompt_name']}]\n  {answer}")

    # ----- Save JSON -----
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now().isoformat(),
        "ollama_url": OLLAMA_BASE_URL,
        "results": all_results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
