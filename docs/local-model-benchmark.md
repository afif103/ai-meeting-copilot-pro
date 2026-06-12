# Local Model Benchmark

The app generates live suggestions with a local Ollama model. Which model you
pick is a trade-off between **speed** (answers must start appearing while the
interviewer is still finishing their sentence) and **quality** (answers must
sound natural and correct). This benchmark measures both on *your* machine so
you can choose with real numbers instead of guesses.

## How to run

```bash
# Benchmark the default candidates (skips any that aren't installed)
python tools/benchmark_ollama_models.py

# Benchmark specific models
python tools/benchmark_ollama_models.py llama3.2:3b qwen2.5-coder:7b

# Download missing (non-heavy) models first, then benchmark
python tools/benchmark_ollama_models.py qwen3:4b qwen3:8b --pull
```

Requirements: Ollama running locally (it starts with Windows automatically).
The script makes only local calls — nothing leaves your machine.

Each model is loaded, warmed up, run against 4 app-realistic prompts
(interview answer, technical explanation, transcript refine, follow-up
suggestion), then unloaded so the next model gets full GPU memory.

Results are printed as a table and saved to `data/benchmark_results.json`
(gitignored, includes the full answer texts).

## Reading the results

| Metric | Meaning | Good for live use |
|--------|---------|-------------------|
| LOAD | Cold-load time, first use per session | under ~10s |
| MEM / VRAM | Memory while loaded; VRAM < MEM means CPU spill | VRAM should equal MEM |
| TTFT | Time to first token — delay before text appears | **under 0.5s ideal, under 1s ok** |
| TOTAL | Time for the complete answer | under ~10s for 400 tokens |
| TOK/S | Generation speed | 20+ keeps ahead of reading speed |
| MAXGAP | Longest stall between chunks (streaming smoothness) | under ~0.5s |

TTFT is the metric that matters most in a live interview — it's the gap
between the question landing and you having something to read.

**Quality is not a number.** The script prints each model's actual answers —
read them and judge: does it sound like a person? Does it answer directly?
Does it follow the length/format instructions? A fast model that rambles or
ignores instructions loses to a slightly slower one that nails the answer.

## Candidate models

| Model | Download | Notes |
|-------|----------|-------|
| llama3.2:3b | 2.0 GB | Current refine model. Fast baseline. |
| qwen2.5-coder:7b | 4.7 GB | Current suggest model. Coding-tuned (odd fit for conversational answers). |
| qwen3:4b | ~2.6 GB | Newer generation, strong for its size. |
| qwen3:8b | ~5.2 GB | Quality candidate; still fits an 8 GB GPU. |
| gemma3:4b | ~3.3 GB | Optional alternative candidate. |
| qwen3:14b | ~9.3 GB | **Heavy.** Exceeds 8 GB VRAM → CPU spill → slow TTFT. Manual pull only. |
| qwen3:30b-a3b | ~18 GB | **Heavy.** MoE (3B active) so CPU-tolerable, but big download and RAM-hungry. Manual pull only, experimental. |

The script never downloads heavy models — pull them yourself
(`ollama pull qwen3:14b`) if you decide the speed cost is worth testing.

### This PC (RTX 3060 8 GB VRAM, 32 GB RAM)

Models up to ~5.5 GB load fully into VRAM and stream fast. `qwen3:14b` will
split between GPU and CPU — expect a noticeably worse TTFT, likely outside
live-use range. `qwen3:30b-a3b` fits in system RAM and its MoE design keeps
generation usable, but treat it as an offline-quality experiment, not a live
interview default.

## Applying the winner

No code changes needed — set the model in `.env` and restart the app:

```
OLLAMA_MODEL_SUGGEST=qwen3:8b      # the model that answers
OLLAMA_MODEL_REFINE=llama3.2:3b    # the model that cleans transcripts
```

Keep the refine model small and fast: it runs before every suggestion, so its
latency adds directly to the total response time.
