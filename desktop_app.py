"""
AI Meeting Copilot Pro - Ultimate Desktop Application
World-class real-time transcription and AI suggestion system
Advanced features: Smart processing, async operations, intelligent caching
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from backend.vector_store import LocalVectorStore
from backend.audio_capture import AudioCapture
from backend.transcription import TranscriptionService
from backend.anonymizer import anonymize_transcript as anonymize_text
from backend.grok_client import (
    LLM_PROVIDER,
    generate_suggestion,
    generate_suggestion_stream,
    refine_transcript,
)
from backend.memory_store import ensure_memory_files

# UI default for the Groq/Ollama toggle, driven by LLM_PROVIDER in .env
DEFAULT_LLM_MODE = "groq" if LLM_PROVIDER == "groq" else "ollama"

import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, simpledialog, ttk
import threading
import time
import queue
import hashlib
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import json


class AICoplotPro:
    """Ultimate AI Meeting Copilot with advanced features"""

    def __init__(self, username="default"):
        self.root = tk.Tk()
        self.root.title("AI Meeting Copilot Pro")
        self.root.configure(bg="#1e1e2e")

        # Core state
        self.username = username
        self.live_merge_str = ""  # Full accumulated text
        self.new_speech_buffer = ""  # Only new speech since last processing
        self.is_finalizing = False
        self.last_input_time = time.time()
        self.last_process_position = 0  # Track what we've already processed
        self.speech_length = 0
        self.context = "Technical discussion context"
        self.suggestion_cache = {}
        self.recent_hashes = deque(maxlen=20)
        self.capture = None
        self.transcriber = None
        self.vector_store = None
        self.nlp = None
        self.is_processing = False
        self.last_suggestion_time = 0
        self.suggestion_queue = queue.Queue()
        self._streaming_start_pos = "1.0"  # For streaming UI

        # Performance metrics
        self.metrics = {
            "session_start": time.time(),
            "transcription_count": 0,
            "suggestion_count": 0,
            "total_transcription_time": 0,
            "total_suggestion_time": 0,
            "cache_hits": 0,
            "api_calls": 0,
        }

        # Build modern UI
        self._create_ui()
        self._setup_window()
        self._start_workers()

    def _create_ui(self):
        """Create modern, professional UI with split view"""
        # Grid configuration - 2 columns for split view
        self.root.grid_rowconfigure(0, weight=0)  # Control panel
        self.root.grid_rowconfigure(1, weight=1)  # Main content
        self.root.grid_rowconfigure(2, weight=0)  # History label
        self.root.grid_rowconfigure(3, weight=1)  # History
        self.root.grid_columnconfigure(0, weight=1)  # Left column (transcript)
        self.root.grid_columnconfigure(1, weight=1)  # Right column (suggestion)

        # CONTROL PANEL (spans both columns)
        ctrl = tk.Frame(self.root, bg="#2a2a3e", relief=tk.RAISED, bd=2)
        ctrl.grid(row=0, column=0, columnspan=2, sticky="ew", pady=2, padx=2)

        self.status_lbl = tk.Label(
            ctrl,
            text="Ready",
            bg="#2a2a3e",
            fg="#00ff00",
            font=("Segoe UI", 9, "bold"),
        )
        self.status_lbl.pack(side=tk.LEFT, padx=5)

        self.device_lbl = tk.Label(
            ctrl,
            text="Device: Init...",
            bg="#2a2a3e",
            fg="#fff",
            font=("Segoe UI", 8),
        )
        self.device_lbl.pack(side=tk.LEFT, padx=5)

        # Audio source toggle
        self.audio_source_var = tk.StringVar(value="system")
        audio_src_frm = tk.Frame(ctrl, bg="#2a2a3e")
        audio_src_frm.pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(
            audio_src_frm, text="System", variable=self.audio_source_var,
            value="system", bg="#2a2a3e", fg="#fff", selectcolor="#3a3a4e",
            font=("Segoe UI", 8), command=self._on_audio_source_change
        ).pack(side=tk.LEFT, padx=1)
        tk.Radiobutton(
            audio_src_frm, text="Mic", variable=self.audio_source_var,
            value="microphone", bg="#2a2a3e", fg="#fff", selectcolor="#3a3a4e",
            font=("Segoe UI", 8), command=self._on_audio_source_change
        ).pack(side=tk.LEFT, padx=1)

        self.proc_lbl = tk.Label(
            ctrl, text="", bg="#2a2a3e", fg="#ffa500", font=("Segoe UI", 8, "bold")
        )
        self.proc_lbl.pack(side=tk.LEFT, padx=5)

        self.audio_quality_lbl = tk.Label(
            ctrl, text="Audio: --", bg="#2a2a3e", fg="#aaa", font=("Segoe UI", 8)
        )
        self.audio_quality_lbl.pack(side=tk.LEFT, padx=5)

        self.username_lbl = tk.Label(
            ctrl,
            text=f"User: {self.username}",
            bg="#3a3a4e",
            fg="#00d4ff",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=2,
        )
        self.username_lbl.pack(side=tk.LEFT, padx=5)

        # LLM selector (defaults to LLM_PROVIDER from .env; Ollama = local)
        self.llm_var = tk.StringVar(value=DEFAULT_LLM_MODE)
        llm_frm = tk.Frame(ctrl, bg="#2a2a3e")
        llm_frm.pack(side=tk.LEFT, padx=10)

        tk.Radiobutton(
            llm_frm,
            text="Groq",
            variable=self.llm_var,
            value="groq",
            bg="#2a2a3e",
            fg="#fff",
            selectcolor="#3a3a4e",
            font=("Segoe UI", 8),
        ).pack(side=tk.LEFT, padx=2)
        tk.Radiobutton(
            llm_frm,
            text="Ollama",
            variable=self.llm_var,
            value="ollama",
            bg="#2a2a3e",
            fg="#fff",
            selectcolor="#3a3a4e",
            font=("Segoe UI", 8),
        ).pack(side=tk.LEFT, padx=2)

        # Persona selector
        tk.Label(
            ctrl,
            text="Persona:",
            bg="#2a2a3e",
            fg="#fff",
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=5)

        self.persona_var = tk.StringVar(value="rami_ai_engineer")
        self.custom_prompt = ""  # Store custom prompt

        # Persona display names
        persona_display = {
            "rami_ai_engineer": "Rami - AI Engineer",
            "rami_ai_interview": "Rami - AI Interview",
            "rami_fullstack_interview": "Rami - Full-Stack Interview",
            "rami_interview_memory": "Rami - Interview (Memory)",
            "call_center_professional": "Call Center Pro (38yr)",
            "call_center_learner": "Call Center Learner (18yr)",
            "custom": "Custom Prompt"
        }

        persona_combo = ttk.Combobox(
            ctrl,
            textvariable=self.persona_var,
            values=list(persona_display.keys()),
            width=25,
            state="readonly",
            font=("Segoe UI", 8)
        )
        persona_combo.pack(side=tk.LEFT, padx=5)

        # Edit button for custom prompt
        self.edit_prompt_btn = tk.Button(
            ctrl,
            text="Edit",
            bg="#4a4a5e",
            fg="#fff",
            font=("Segoe UI", 8),
            relief=tk.FLAT,
            cursor="hand2",
            command=self._open_custom_prompt_editor
        )
        self.edit_prompt_btn.pack(side=tk.LEFT, padx=2)

        # Update display when persona changes
        def update_persona_display(*args):
            current = self.persona_var.get()
            if current in persona_display:
                print(f"[PERSONA] Changed to: {persona_display[current]}")
            # Show edit button only for custom persona
            if current == "custom":
                self.edit_prompt_btn.config(bg="#00aa00")
            else:
                self.edit_prompt_btn.config(bg="#4a4a5e")

        self.persona_var.trace('w', update_persona_display)

        # Action buttons
        btn_frm = tk.Frame(ctrl, bg="#2a2a3e")
        btn_frm.pack(side=tk.RIGHT, padx=5)

        btn_style = {
            "font": ("Segoe UI", 8, "bold"),
            "relief": tk.FLAT,
            "cursor": "hand2",
            "padx": 8,
            "pady": 3,
        }

        tk.Button(
            btn_frm,
            text="Finalize",
            command=self.finalize,
            bg="#28a745",
            fg="white",
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)

        self.pause_btn = tk.Button(
            btn_frm,
            text="Pause",
            command=self.toggle_rec,
            bg="#ffc107",
            fg="black",
            **btn_style,
        )
        self.pause_btn.pack(side=tk.LEFT, padx=2)

        tk.Button(
            btn_frm,
            text="Upload",
            command=self.upload_doc,
            bg="#007bff",
            fg="white",
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btn_frm,
            text="User",
            command=self.change_user,
            bg="#6c757d",
            fg="white",
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btn_frm,
            text="Save",
            command=self.save_session,
            bg="#28a745",
            fg="white",
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btn_frm,
            text="Load",
            command=self.load_session,
            bg="#6610f2",
            fg="white",
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btn_frm,
            text="Export",
            command=self.export_session,
            bg="#fd7e14",
            fg="white",
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btn_frm,
            text="Stats",
            command=self.show_stats,
            bg="#20c997",
            fg="white",
            **btn_style,
        ).pack(side=tk.LEFT, padx=2)

        # LEFT COLUMN: LIVE TRANSCRIPT
        trans_label = tk.Label(
            self.root,
            text="Live Transcript",
            bg="#1e1e2e",
            fg="#00d4ff",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        trans_label.grid(row=1, column=0, sticky="ew", padx=(5, 2), pady=(5, 0))

        self.trans_txt = scrolledtext.ScrolledText(
            self.root,
            font=("Consolas", 11),
            wrap=tk.WORD,
            bg="#2b2b3e",
            fg="#e0e0e0",
            insertbackground="#00d4ff",
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        self.trans_txt.grid(row=1, column=0, sticky="nsew", padx=(5, 2), pady=(25, 5))

        # RIGHT COLUMN: AI SUGGESTION
        sugg_label = tk.Label(
            self.root,
            text="AI Suggestion",
            bg="#1e1e2e",
            fg="#00ff00",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        sugg_label.grid(row=1, column=1, sticky="ew", padx=(2, 5), pady=(5, 0))

        self.sugg_txt = scrolledtext.ScrolledText(
            self.root,
            font=("Segoe UI", 12),
            wrap=tk.WORD,
            bg="#1a1a2e",
            fg="#00ff00",
            insertbackground="#00ff00",
            relief=tk.FLAT,
            padx=15,
            pady=15,
        )
        self.sugg_txt.grid(row=1, column=1, sticky="nsew", padx=(2, 5), pady=(25, 5))

        # HISTORY (spans both columns)
        tk.Label(
            self.root,
            text="History",
            bg="#1e1e2e",
            fg="#ffa500",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(5, 0))

        self.hist_txt = scrolledtext.ScrolledText(
            self.root,
            font=("Segoe UI", 9),
            wrap=tk.WORD,
            bg="#252535",
            fg="#d0d0d0",
            relief=tk.FLAT,
            padx=10,
            pady=10,
            height=8,
        )
        self.hist_txt.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)

    def _setup_window(self):
        """Setup window geometry and properties"""
        self.root.geometry("1400x900")
        self.root.attributes("-topmost", True)
        self.root.update_idletasks()

        w, h = 1400, 900
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _start_workers(self):
        """Start background workers"""

        # Suggestion processor
        def process_worker():
            while True:
                try:
                    trans = self.suggestion_queue.get(timeout=1)
                    self._process_async(trans)
                except queue.Empty:
                    continue

        threading.Thread(target=process_worker, daemon=True).start()

        # Animation
        def animate():
            frames = ["Working", "Working.", "Working..", "Working..."]
            idx = 0
            while True:
                try:
                    if self.is_processing:
                        # Schedule UI update in main thread
                        self.root.after(0, lambda i=idx: self.proc_lbl.config(text=frames[i]))
                        idx = (idx + 1) % len(frames)
                    else:
                        self.root.after(0, lambda: self.proc_lbl.config(text=""))
                except Exception:
                    pass  # Ignore errors if window is closing
                time.sleep(0.3)

        threading.Thread(target=animate, daemon=True).start()

        # Audio quality monitor
        def monitor_audio_quality():
            while True:
                if self.capture:
                    try:
                        # Get recent audio level from capture
                        level = getattr(self.capture, 'current_audio_level', 0)

                        # Determine quality status
                        if level < 0.01:
                            status = "Audio: None"
                            color = "#ff0000"
                        elif level < 0.1:
                            status = "Audio: Low"
                            color = "#ffa500"
                        elif level < 0.5:
                            status = "Audio: Good"
                            color = "#00ff00"
                        else:
                            status = "Audio: Loud"
                            color = "#00d4ff"

                        self.audio_quality_lbl.config(text=status, fg=color)
                    except:
                        pass
                time.sleep(0.5)

        threading.Thread(target=monitor_audio_quality, daemon=True).start()

        # Inactivity checker
        self.check_inactivity()

    def set_capture(self, capture):
        """Setup audio capture"""
        self.capture = capture
        if capture:
            info = capture.get_device_info()
            name = info.get("name", "Unknown")[:30]
            self.device_lbl.config(text=f"Device: {name}")
            self._set_status("Listening", "#00ff00")
        print("Capture ready")

    def set_transcriber(self, transcriber):
        """Setup transcriber"""
        self.transcriber = transcriber
        try:
            import spacy
            self.nlp = spacy.load("en_core_web_sm")
            print("SpaCy loaded")
        except:
            print("SpaCy not available")
        print("Transcriber ready")

    def _set_status(self, status, color="#ffffff"):
        """Update status label"""
        self.status_lbl.config(text=status, fg=color)

    def _on_audio_source_change(self):
        """Switch audio source between system and microphone"""
        source = self.audio_source_var.get()
        print(f"[AUDIO] Switching to: {source}")
        if self.capture:
            self.capture.set_audio_source(source)
            # Update device label
            device_name = self.capture.device_info.get("name", "Unknown")
            self.device_lbl.config(text=f"Device: {device_name[:30]}")

    def _open_custom_prompt_editor(self):
        """Open popup window to edit custom prompt"""
        editor = tk.Toplevel(self.root)
        editor.title("Custom Prompt Editor")
        editor.geometry("700x500")
        editor.configure(bg="#1e1e2e")
        editor.transient(self.root)
        editor.grab_set()

        # Instructions
        tk.Label(
            editor,
            text="Paste your custom prompt below. Use {snippet} for the transcript and {context_summary} for context.",
            bg="#1e1e2e",
            fg="#aaa",
            font=("Segoe UI", 9),
            wraplength=680
        ).pack(pady=10, padx=10)

        # Text area
        text_frame = tk.Frame(editor, bg="#1e1e2e")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        text_area = scrolledtext.ScrolledText(
            text_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#2a2a3e",
            fg="#fff",
            insertbackground="#fff"
        )
        text_area.pack(fill=tk.BOTH, expand=True)

        # Load existing custom prompt
        if self.custom_prompt:
            text_area.insert("1.0", self.custom_prompt)
        else:
            # Default template
            default_template = """You are an AI assistant helping the user respond in a conversation.

### CONTEXT
{context_summary}

### WHAT WAS SAID
{snippet}

### YOUR JOB
Suggest what the user should say in response. Be concise and helpful.

### RULES
- Write ONLY what the user should say (direct speech)
- Keep it short (1-3 sentences)
- Be natural and conversational"""
            text_area.insert("1.0", default_template)

        # Button frame
        btn_frame = tk.Frame(editor, bg="#1e1e2e")
        btn_frame.pack(pady=10)

        def save_and_close():
            self.custom_prompt = text_area.get("1.0", tk.END).strip()
            self.persona_var.set("custom")
            print(f"[PERSONA] Custom prompt saved ({len(self.custom_prompt)} chars)")
            editor.destroy()

        def cancel():
            editor.destroy()

        tk.Button(
            btn_frame,
            text="Save & Use",
            bg="#00aa00",
            fg="#fff",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            padx=20,
            command=save_and_close
        ).pack(side=tk.LEFT, padx=10)

        tk.Button(
            btn_frame,
            text="Cancel",
            bg="#666",
            fg="#fff",
            font=("Segoe UI", 10),
            relief=tk.FLAT,
            cursor="hand2",
            padx=20,
            command=cancel
        ).pack(side=tk.LEFT, padx=10)

        # Focus the text area
        text_area.focus_set()

    def update_live_transcript(self, transcript):
        """Update live transcript with smart processing - ONLY NEW SPEECH"""
        # Add to full transcript
        self.live_merge_str += " " + transcript

        # Add to new speech buffer (for processing)
        self.new_speech_buffer += " " + transcript

        self.last_input_time = time.time()
        self.speech_length += len(transcript.split())

        # Track transcription metrics
        self.metrics["transcription_count"] += 1

        # Display with smart truncation (show full conversation)
        text = self.live_merge_str.strip()
        if len(text) > 3000:
            text = "...\n" + text[-2800:]

        # Update transcript panel
        self.trans_txt.delete(1.0, tk.END)
        self.trans_txt.insert(tk.END, text)
        self.trans_txt.see(tk.END)

        # Auto-process check
        self._check_auto_process()

    def _check_auto_process(self):
        """ADAPTIVE auto-processing - faster triggers for smoother conversation"""
        if self.is_processing or not self.new_speech_buffer.strip():
            return

        text = self.new_speech_buffer.strip()
        words = len(text.split())

        # Count sentences in NEW speech only
        sents = text.count(".") + text.count("!") + text.count("?")
        if self.nlp:
            try:
                sents = len(list(self.nlp(text).sents))
            except:
                pass

        idle = time.time() - self.last_input_time
        since_last_sugg = time.time() - self.last_suggestion_time

        # ADAPTIVE TIMING based on utterance length
        # Longer utterances = process faster (user is clearly speaking)
        # Shorter utterances = wait a bit more (might not be done)
        if words >= 25:
            trigger_delay = 1.0  # Long utterance - process quickly
        elif words >= 15:
            trigger_delay = 1.3  # Medium-long - slightly faster
        elif words >= 8:
            trigger_delay = 1.6  # Medium - moderate wait
        else:
            trigger_delay = 2.0  # Short - wait for more

        # Also trigger on complete sentences faster
        sentence_delay = 1.2 if sents >= 2 else 1.5

        should_process = (
            (words >= 5 and idle > trigger_delay) or  # Adaptive timing
            (sents >= 1 and idle > sentence_delay) or  # Faster on sentences
            (words >= 20)  # Hard limit - process immediately
        )

        # Allow suggestions more frequently (was 2s, now 1.5s)
        if should_process and since_last_sugg > 1.5:
            self.process_text()

    def process_text(self):
        """Queue NEW speech for processing"""
        if self.is_processing:
            return

        # Only process NEW speech buffer
        text = self.new_speech_buffer.strip()
        
        if not text:
            return
        
        h = hashlib.md5(text.encode()).hexdigest()

        if h in self.recent_hashes:
            return

        self.recent_hashes.append(h)
        self.is_processing = True
        self.last_suggestion_time = time.time()
        self.suggestion_queue.put(text)

    def _process_async(self, transcript):
        """Async processing with PARALLEL operations for faster response"""
        print(f"Processing NEW speech: {transcript[:100]}...")

        start_time = time.time()

        try:
            use_ollama = self.llm_var.get() == "ollama"
            self.root.after(0, lambda: self._set_status("Processing...", "#ffa500"))

            # PARALLEL STEP: Run refine AND vector search simultaneously
            refined = transcript
            vector_docs = []

            with ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both tasks in parallel
                refine_future = executor.submit(
                    self._safe_refine, transcript, use_ollama
                )
                vector_future = executor.submit(
                    self._safe_vector_search, transcript
                )

                # Wait for both to complete
                refined = refine_future.result()
                vector_docs = vector_future.result()

            print(f"Refined + Vector search done (parallel)")

            # Step 2: Anonymize (fast, no need to parallelize)
            snippet = anonymize_text(refined)
            print(f"Anonymized")

            # Step 3: Build context with pre-fetched vector docs
            self.root.after(0, lambda: self._set_status("Generating...", "#ffa500"))
            context = self._build_context_with_docs(vector_docs)
            cache_key = hashlib.md5(f"{snippet}_{context[:300]}".encode()).hexdigest()

            suggestion = ""

            if cache_key in self.suggestion_cache:
                suggestion = self.suggestion_cache[cache_key]
                print("From cache")
                self.metrics["cache_hits"] += 1
                # Update UI with cached suggestion (non-streaming)
                self.root.after(
                    0, lambda: self._update_ui(transcript, refined, snippet, suggestion)
                )
            else:
                self.metrics["api_calls"] += 1
                # STREAMING: Update UI as tokens arrive
                print("Generating (streaming)...")

                # Clear suggestion area first
                self.root.after(0, lambda: self._prepare_streaming_ui(transcript, refined, snippet))

                # Stream tokens
                full_suggestion = ""
                for token in generate_suggestion_stream(
                    context,
                    snippet,
                    use_ollama=use_ollama,
                    persona=self.persona_var.get(),
                    custom_prompt=self.custom_prompt if self.persona_var.get() == "custom" else None
                ):
                    if token:
                        full_suggestion += token
                        # Update UI with each token
                        self.root.after(0, lambda t=token: self._append_streaming_token(t))

                suggestion = full_suggestion
                self.suggestion_cache[cache_key] = suggestion

                # Limit cache
                if len(self.suggestion_cache) > 100:
                    for _ in range(20):
                        self.suggestion_cache.pop(next(iter(self.suggestion_cache)))
                print("Generated (streaming complete)")

                # Finalize UI
                self.root.after(0, lambda: self._finalize_streaming_ui())

            # Save
            self._save_memory(transcript, refined, snippet, suggestion)

            # CRITICAL: Clear NEW speech buffer after processing
            self.new_speech_buffer = ""

            # Reset state
            self.speech_length = 0
            self.is_finalizing = False
            self.root.after(0, lambda: self._set_status("Ready", "#00ff00"))

            # Track metrics
            elapsed = time.time() - start_time
            self.metrics["suggestion_count"] += 1
            self.metrics["total_suggestion_time"] += elapsed
            print(f"[METRICS] Suggestion completed in {elapsed:.2f}s")

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            self.root.after(0, lambda: self._set_status("Error", "#ff0000"))
        finally:
            self.is_processing = False

    def _safe_refine(self, transcript, use_ollama):
        """Safe refine with retry logic"""
        for attempt in range(2):
            try:
                return refine_transcript(transcript, use_ollama=use_ollama)
            except Exception as e:
                if attempt == 0:
                    print(f"Retry refine...")
                    time.sleep(1)
        return transcript  # Fallback to original

    def _safe_vector_search(self, query):
        """Safe vector search with caching"""
        if not self.vector_store:
            return []
        try:
            results = self.vector_store.search(query, k=2)
            return [r["page_content"] for r in results] if results else []
        except Exception as e:
            print(f"Vector search error: {e}")
            return []

    def _build_context_with_docs(self, vector_docs):
        """Build context using pre-fetched vector docs"""
        # Use last 500 chars of FULL conversation for context
        recent_convo = self.live_merge_str[-500:] if len(self.live_merge_str) > 500 else self.live_merge_str
        ctx = f"Conversation context: {recent_convo}"

        # Add recent history (last 2 suggestions)
        recent = self.hist_txt.get(1.0, "3.0")
        if recent.strip():
            ctx += f"\n\nRecent suggestions: {recent[:200]}"

        # Add pre-fetched vector store context
        if vector_docs:
            ctx += f"\n\nRelevant docs: {vector_docs[0][:200]}"

        return ctx

    
    def _update_ui(self, trans, ref, snip, sugg):
        """Update UI with results - shows in suggestion panel"""
        try:
            # Clear and update suggestion panel
            self.sugg_txt.delete(1.0, tk.END)
                     
            # Show processing steps
            self.sugg_txt.insert(tk.END, "\n\n--- PROCESSING DETAILS ---\n\n", "header")
            self.sugg_txt.insert(tk.END, "Original:\n", "label")
            self.sugg_txt.insert(tk.END, f"{trans}\n\n")
            self.sugg_txt.insert(tk.END, "Refined:\n", "label")
            self.sugg_txt.insert(tk.END, f"{ref}\n\n")
            self.sugg_txt.insert(tk.END, "Anonymized:\n", "label")
            self.sugg_txt.insert(tk.END, f"{snip}\n\n")
            self.sugg_txt.insert(tk.END, "--------------------------\n\n", "separator")
            self.sugg_txt.insert(tk.END, "AI SUGGESTION:\n\n", "suggestion_header")

            # Add suggestion with typewriter effect
            words = sugg.split()
            for i, word in enumerate(words):
                self.sugg_txt.insert(tk.END, word + " ", "suggestion")
                if i % 5 == 0:
                    self.sugg_txt.update()
                    time.sleep(0.01)

          
            # Scroll to show suggestion
            self.sugg_txt.see(tk.END)

            # Add to history
            ts = datetime.now().strftime("%H:%M:%S")
            entry = f"[{ts}] {sugg}\n{'-'*100}\n"
            self.hist_txt.insert(1.0, entry)

            # Visual feedback
            self.root.lift()
            self.root.focus_force()
            self._flash_border()

            print("UI updated")
        except Exception as e:
            print(f"UI error: {e}")

    def _prepare_streaming_ui(self, trans, ref, snip):
        """Prepare UI for streaming response"""
        try:
            # Clear and update suggestion panel
            self.sugg_txt.delete(1.0, tk.END)

            # Show processing steps (collapsed version for streaming)
            self.sugg_txt.insert(tk.END, "\n\n--- PROCESSING ---\n", "header")
            self.sugg_txt.insert(tk.END, f"Original: {trans[:80]}...\n", "small")
            self.sugg_txt.insert(tk.END, f"Refined: {ref[:80]}...\n", "small")
            self.sugg_txt.insert(tk.END, f"Anonymized: {snip[:80]}...\n\n", "small")
            self.sugg_txt.insert(tk.END, "AI SUGGESTION (streaming):\n\n", "suggestion_header")

            # Store position where suggestion starts
            self._streaming_start_pos = self.sugg_txt.index(tk.END)

            print("UI prepared for streaming")
        except Exception as e:
            print(f"Streaming UI prep error: {e}")

    def _append_streaming_token(self, token):
        """Append a single token to the streaming suggestion"""
        try:
            self.sugg_txt.insert(tk.END, token, "suggestion")
            self.sugg_txt.see(tk.END)
            self.sugg_txt.update_idletasks()
        except Exception as e:
            print(f"Streaming token error: {e}")

    def _finalize_streaming_ui(self):
        """Finalize streaming UI after all tokens received"""
        try:
            # Get the full suggestion that was streamed
            suggestion_text = self.sugg_txt.get(self._streaming_start_pos, tk.END).strip()

            # Add to history
            ts = datetime.now().strftime("%H:%M:%S")
            entry = f"[{ts}] {suggestion_text}\n{'-'*100}\n"
            self.hist_txt.insert(1.0, entry)

            # Visual feedback
            self.root.lift()
            self.root.focus_force()
            self._flash_border()

            print("Streaming UI finalized")
        except Exception as e:
            print(f"Streaming finalize error: {e}")

    def _flash_border(self):
        """Flash window border"""
        orig = self.root.cget("bg")
        self.root.config(bg="#00ff00")
        self.root.after(100, lambda: self.root.config(bg=orig))

    def _save_memory(self, trans, ref, anon, sugg):
        """Save to memory"""
        try:
            os.makedirs("data", exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Markdown
            with open("record.md", "a", encoding="utf-8") as f:
                f.write(f"\n## [{ts}]\n\n**Transcript:** {trans}\n\n")
                f.write(f"**Refined:** {ref}\n\n**Anonymized:** {anon}\n\n")
                f.write(f"**Suggestion:** {sugg}\n\n---\n\n")

            # JSON
            json_file = f"data/history_{datetime.now().strftime('%Y%m%d')}.json"
            entry = {
                "timestamp": ts,
                "transcript": trans,
                "refined": ref,
                "anonymized": anon,
                "suggestion": sugg,
                "user": self.username,
            }

            data = []
            if os.path.exists(json_file):
                with open(json_file, "r") as f:
                    data = json.load(f)
            data.append(entry)

            with open(json_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Save error: {e}")

    def check_inactivity(self):
        """Periodic inactivity check"""
        self.root.after(1000, self.check_inactivity)

    def finalize(self):
        """Manual finalization"""
        if not self.new_speech_buffer.strip() or self.is_processing:
            messagebox.showinfo("Info", "Nothing to finalize or processing active")
            return

        if messagebox.askyesno("Finalize", "Process current speech?"):
            self.process_text()

    def toggle_rec(self):
        """Toggle recording"""
        if not self.capture:
            messagebox.showwarning("Warning", "Capture not initialized")
            return

        if not self.capture.paused:
            self.capture.paused = True
            self.pause_btn.config(text="Resume", bg="#28a745")
            self._set_status("Paused", "#ff6b6b")
        else:
            self.capture.paused = False
            self.pause_btn.config(text="Pause", bg="#ffc107")
            self._set_status("Listening", "#00ff00")

    def upload_doc(self):
        """Upload document, resume, or data to vector store"""
        path = filedialog.askopenfilename(
            title="Select Document (Resume, PDF, Text, JSON, Markdown)",
            filetypes=[
                ("All Supported", "*.txt *.pdf *.json *.md *.csv"),
                ("Text Files", "*.txt"),
                ("PDF Files", "*.pdf"),
                ("JSON Files", "*.json"),
                ("Markdown", "*.md"),
                ("CSV Files", "*.csv"),
            ],
        )

        if not path:
            return

        try:
            self._set_status("Reading file...", "#ffa500")
            filename = os.path.basename(path)
            text = ""

            # Extract text based on file type
            if path.endswith(".pdf"):
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(path)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                except ImportError:
                    messagebox.showerror("Error", "PyPDF2 not installed. Run: pip install PyPDF2")
                    return
            elif path.endswith(".json"):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    # Handle different JSON structures
                    if isinstance(data, list):
                        text = "\n".join(str(item) for item in data)
                    elif isinstance(data, dict):
                        text = json.dumps(data, indent=2)
                    else:
                        text = str(data)
            elif path.endswith(".csv"):
                import csv
                with open(path, encoding="utf-8") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    text = "\n".join([", ".join(row) for row in rows])
            else:  # .txt, .md, or other text files
                with open(path, encoding="utf-8") as f:
                    text = f.read()

            if not text.strip():
                messagebox.showwarning("Warning", "File appears to be empty")
                self._set_status("Ready", "#00ff00")
                return

            # Add to vector store
            if self.vector_store:
                self._set_status("Adding to knowledge base...", "#ffa500")

                # Determine document type for better indexing
                doc_type = "document"
                lower_name = filename.lower()
                if "resume" in lower_name or "cv" in lower_name:
                    doc_type = "resume"
                elif "project" in lower_name:
                    doc_type = "project"
                elif "notes" in lower_name:
                    doc_type = "notes"

                # Add with metadata prefix for context
                prefixed_text = f"[{doc_type.upper()}: {filename}]\n{text}"

                # Chunk and add (500 chars with 50 overlap for better context)
                chunk_size = 500
                overlap = 50
                chunks_added = 0

                for i in range(0, len(prefixed_text), chunk_size - overlap):
                    chunk = prefixed_text[i:i + chunk_size]
                    if chunk.strip():
                        self.vector_store.add_experience(chunk)
                        chunks_added += 1

                # Clear cache to ensure new docs are found
                self.vector_store.clear_cache()

                messagebox.showinfo(
                    "Success",
                    f"Added '{filename}' to knowledge base\n"
                    f"Type: {doc_type}\n"
                    f"Chunks: {chunks_added}\n"
                    f"Characters: {len(text):,}"
                )
            else:
                messagebox.showwarning("Warning", "Vector store not initialized")

            self._set_status("Ready", "#00ff00")

        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to upload: {str(e)}")
            self._set_status("Error", "#ff0000")

    def change_user(self):
        """Change user and switch to their vector store"""
        new_user = simpledialog.askstring("Change User", "Enter username:")
        if new_user and new_user.strip():
            new_user = new_user.strip()
            old_user = self.username

            try:
                # Update username
                self.username = new_user

                # Update UI label
                self.username_lbl.config(text=f"User: {new_user}")

                # Save to config file
                config_file = "data/user_config.txt"
                os.makedirs("data", exist_ok=True)
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write(new_user)

                # Reinitialize vector store for new user
                print(f"[USER] Switching from '{old_user}' to '{new_user}'...")
                self.vector_store = LocalVectorStore(new_user)
                self.vector_store.load_documents()
                self.vector_store.add_meeting_transcripts()
                self.vector_store.add_project_docs()
                print(f"[USER] Vector store initialized for '{new_user}'")

                messagebox.showinfo(
                    "Success",
                    f"User changed to: {new_user}\n\nVector store switched successfully.\n\nNote: New user has their own isolated knowledge base."
                )

            except Exception as e:
                # Rollback on error
                self.username = old_user
                self.username_lbl.config(text=f"User: {old_user}")
                messagebox.showerror("Error", f"Failed to change user: {str(e)}")
                print(f"[ERROR] User change failed: {e}")

    def test_spk(self):
        """Test speaker"""
        try:
            import winsound
            winsound.Beep(800, 500)
            messagebox.showinfo("Success", "Speaker working")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def save_session(self):
        """Save current session to file"""
        try:
            filename = filedialog.asksaveasfilename(
                title="Save Session",
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
                initialdir="data/sessions",
                initialfile=f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

            if not filename:
                return

            # Create sessions directory if needed
            os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else "data/sessions", exist_ok=True)

            session_data = {
                "timestamp": datetime.now().isoformat(),
                "username": self.username,
                "persona": self.persona_var.get(),
                "live_transcript": self.live_merge_str,
                "history": self.hist_txt.get(1.0, tk.END),
                "metrics": self.metrics.copy(),
                "llm_mode": self.llm_var.get(),
            }

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

            messagebox.showinfo("Success", f"Session saved to:\n{os.path.basename(filename)}")
            print(f"[SAVE] Session saved: {filename}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save session: {str(e)}")
            print(f"[ERROR] Save session failed: {e}")

    def load_session(self):
        """Load a previous session from file"""
        try:
            filename = filedialog.askopenfilename(
                title="Load Session",
                filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
                initialdir="data/sessions"
            )

            if not filename:
                return

            with open(filename, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            # Restore session data
            self.live_merge_str = session_data.get("live_transcript", "")
            history_text = session_data.get("history", "")
            self.llm_var.set(session_data.get("llm_mode", DEFAULT_LLM_MODE))
            self.persona_var.set(session_data.get("persona", "rami_ai_engineer"))

            # Update UI
            self.trans_txt.delete(1.0, tk.END)
            self.trans_txt.insert(tk.END, self.live_merge_str)

            self.hist_txt.delete(1.0, tk.END)
            self.hist_txt.insert(tk.END, history_text)

            # Clear new speech buffer (start fresh)
            self.new_speech_buffer = ""

            session_time = session_data.get("timestamp", "Unknown")
            messagebox.showinfo(
                "Success",
                f"Session loaded from:\n{os.path.basename(filename)}\n\nTimestamp: {session_time}"
            )
            print(f"[LOAD] Session loaded: {filename}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load session: {str(e)}")
            print(f"[ERROR] Load session failed: {e}")

    def export_session(self):
        """Export session to TXT or PDF"""
        try:
            # Ask for format
            export_format = messagebox.askquestion(
                "Export Format",
                "Export as PDF?\n\nYes = PDF\nNo = TXT",
                icon='question'
            )

            if export_format == 'yes':
                # PDF export
                filename = filedialog.asksaveasfilename(
                    title="Export to PDF",
                    defaultextension=".pdf",
                    filetypes=[("PDF", "*.pdf")],
                    initialfile=f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                )

                if filename:
                    self._export_to_pdf(filename)
            else:
                # TXT export
                filename = filedialog.asksaveasfilename(
                    title="Export to TXT",
                    defaultextension=".txt",
                    filetypes=[("Text", "*.txt")],
                    initialfile=f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                )

                if filename:
                    self._export_to_txt(filename)

        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {str(e)}")
            print(f"[ERROR] Export failed: {e}")

    def _export_to_txt(self, filename):
        """Export session to TXT format"""
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write("AI MEETING COPILOT PRO - SESSION TRANSCRIPT\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"User: {self.username}\n")
                f.write(f"Duration: {self._get_session_duration()}\n")
                f.write("\n" + "=" * 80 + "\n")
                f.write("LIVE TRANSCRIPT\n")
                f.write("=" * 80 + "\n\n")
                f.write(self.live_merge_str or "No transcript available.")
                f.write("\n\n" + "=" * 80 + "\n")
                f.write("AI SUGGESTIONS HISTORY\n")
                f.write("=" * 80 + "\n\n")
                f.write(self.hist_txt.get(1.0, tk.END) or "No suggestions available.")
                f.write("\n\n" + "=" * 80 + "\n")
                f.write("PERFORMANCE METRICS\n")
                f.write("=" * 80 + "\n\n")
                f.write(self._format_metrics_text())

            messagebox.showinfo("Success", f"Exported to:\n{os.path.basename(filename)}")
            print(f"[EXPORT] TXT export complete: {filename}")

        except Exception as e:
            raise Exception(f"TXT export error: {e}")

    def _export_to_pdf(self, filename):
        """Export session to PDF format"""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
            from reportlab.lib.enums import TA_LEFT, TA_CENTER

            # Create PDF
            doc = SimpleDocTemplate(filename, pagesize=letter,
                                  topMargin=0.75*inch, bottomMargin=0.75*inch)
            story = []
            styles = getSampleStyleSheet()

            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor='darkblue',
                spaceAfter=12,
                alignment=TA_CENTER
            )
            story.append(Paragraph("AI MEETING COPILOT PRO", title_style))
            story.append(Paragraph("Session Transcript", title_style))
            story.append(Spacer(1, 0.3*inch))

            # Metadata
            meta_style = styles['Normal']
            story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", meta_style))
            story.append(Paragraph(f"<b>User:</b> {self.username}", meta_style))
            story.append(Paragraph(f"<b>Duration:</b> {self._get_session_duration()}", meta_style))
            story.append(Spacer(1, 0.3*inch))

            # Transcript section
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=14,
                textColor='darkgreen',
                spaceAfter=12
            )
            story.append(Paragraph("Live Transcript", heading_style))
            transcript_text = self.live_merge_str or "No transcript available."
            story.append(Paragraph(transcript_text.replace('\n', '<br/>'), styles['Normal']))
            story.append(PageBreak())

            # Suggestions section
            story.append(Paragraph("AI Suggestions History", heading_style))
            history_text = self.hist_txt.get(1.0, tk.END) or "No suggestions available."
            story.append(Paragraph(history_text.replace('\n', '<br/>'), styles['Normal']))
            story.append(PageBreak())

            # Metrics section
            story.append(Paragraph("Performance Metrics", heading_style))
            metrics_text = self._format_metrics_text().replace('\n', '<br/>')
            story.append(Paragraph(metrics_text, styles['Normal']))

            # Build PDF
            doc.build(story)

            messagebox.showinfo("Success", f"PDF exported to:\n{os.path.basename(filename)}")
            print(f"[EXPORT] PDF export complete: {filename}")

        except ImportError:
            messagebox.showerror("Error", "ReportLab not installed.\n\nInstall with: pip install reportlab")
        except Exception as e:
            raise Exception(f"PDF export error: {e}")

    def show_stats(self):
        """Show performance statistics window"""
        try:
            stats_window = tk.Toplevel(self.root)
            stats_window.title("Performance Statistics")
            stats_window.geometry("600x500")
            stats_window.configure(bg="#1e1e2e")

            # Title
            title_lbl = tk.Label(
                stats_window,
                text="📊 Performance Metrics",
                font=("Segoe UI", 16, "bold"),
                bg="#1e1e2e",
                fg="#00d4ff"
            )
            title_lbl.pack(pady=10)

            # Stats text area
            stats_txt = scrolledtext.ScrolledText(
                stats_window,
                font=("Consolas", 10),
                wrap=tk.WORD,
                bg="#2b2b3e",
                fg="#e0e0e0",
                padx=15,
                pady=15
            )
            stats_txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # Build stats content
            stats_content = self._format_metrics_text()
            stats_txt.insert(tk.END, stats_content)
            stats_txt.config(state=tk.DISABLED)

            # Close button
            close_btn = tk.Button(
                stats_window,
                text="Close",
                command=stats_window.destroy,
                bg="#dc3545",
                fg="white",
                font=("Segoe UI", 10, "bold"),
                padx=20,
                pady=5
            )
            close_btn.pack(pady=10)

            print("[STATS] Statistics window opened")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to show stats: {str(e)}")
            print(f"[ERROR] Show stats failed: {e}")

    def _get_session_duration(self):
        """Get formatted session duration"""
        elapsed = time.time() - self.metrics["session_start"]
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _format_metrics_text(self):
        """Format metrics as readable text"""
        avg_suggestion_time = (
            self.metrics["total_suggestion_time"] / self.metrics["suggestion_count"]
            if self.metrics["suggestion_count"] > 0
            else 0
        )

        cache_hit_rate = (
            (self.metrics["cache_hits"] / (self.metrics["cache_hits"] + self.metrics["api_calls"])) * 100
            if (self.metrics["cache_hits"] + self.metrics["api_calls"]) > 0
            else 0
        )

        return f"""SESSION OVERVIEW
----------------
Duration: {self._get_session_duration()}
Started: {datetime.fromtimestamp(self.metrics['session_start']).strftime('%Y-%m-%d %H:%M:%S')}

TRANSCRIPTION
-------------
Total Transcriptions: {self.metrics['transcription_count']}
Total Words: {len(self.live_merge_str.split())}

AI SUGGESTIONS
--------------
Total Suggestions: {self.metrics['suggestion_count']}
Average Response Time: {avg_suggestion_time:.2f}s
Total Processing Time: {self.metrics['total_suggestion_time']:.1f}s

CACHE PERFORMANCE
-----------------
Cache Hits: {self.metrics['cache_hits']}
API Calls: {self.metrics['api_calls']}
Cache Hit Rate: {cache_hit_rate:.1f}%

EFFICIENCY
----------
Suggestions per Minute: {(self.metrics['suggestion_count'] / (time.time() - self.metrics['session_start']) * 60):.1f}
"""

    def run(self):
        """Run main loop"""
        self.check_inactivity()
        self.root.mainloop()


def main():
    """Main entry point"""
    print("AI Meeting Copilot Pro Starting...")

    # Setup
    os.makedirs("data", exist_ok=True)

    # Interview memory files (templates created once, never overwritten)
    created = ensure_memory_files()
    if created:
        print(f"Created memory templates in data/memory: {', '.join(created)}")

    # User selection
    username = "default"
    config_file = "data/user_config.txt"

    if os.path.exists(config_file):
        with open(config_file) as f:
            username = f.read().strip()
        print(f"User: {username}")
    else:
        root = tk.Tk()
        root.withdraw()
        username = simpledialog.askstring("User", "Enter username:") or "default"
        root.destroy()
        with open(config_file, "w") as f:
            f.write(username)

    # Initialize
    print("Initializing...")
    vector_store = LocalVectorStore(username)
    vector_store.load_documents()
    vector_store.add_meeting_transcripts()
    vector_store.add_project_docs()
    print("Vector store ready")

    window = AICoplotPro(username)
    window.vector_store = vector_store
    print("Window ready")

    capture = AudioCapture()
    capture.start_capture()
    window.set_capture(capture)
    print("Capture ready")

    transcriber = TranscriptionService()
    transcriber.start_transcription()
    window.set_transcriber(transcriber)
    print("Transcriber ready")

    # Audio feed thread
    def feed_audio():
        while True:
            chunk = capture.get_audio_chunk()
            if chunk:
                transcriber.add_audio_chunk(chunk)
            time.sleep(0.01)

    threading.Thread(target=feed_audio, daemon=True).start()

    # Process loop
    last_trans = ""

    def process():
        nonlocal last_trans
        trans = transcriber.get_transcript()
        if trans and trans != last_trans and not capture.paused:
            last_trans = trans
            window.update_live_transcript(trans)
        window.root.after(1000, process)

    window.root.after(1000, process)

    # Hotkeys
    try:
        import keyboard
        keyboard.add_hotkey("ctrl+shift+g", lambda: window.root.deiconify())
        keyboard.add_hotkey("ctrl+shift+p", window.toggle_rec)
        print("Hotkeys: Ctrl+Shift+G (show), Ctrl+Shift+P (pause)")
    except:
        print("Hotkeys unavailable")

    print("Ready! Listening...")
    window.run()


if __name__ == "__main__":
    main()