import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from backend.vector_store import LocalVectorStore
from backend.audio_capture import AudioCapture
from backend.transcription import TranscriptionService
from backend.anonymizer import anonymize_transcript as anonymize_text
from backend.grok_client import generate_suggestion, refine_transcript

import tkinter as tk
from tkinter import scrolledtext, ttk, filedialog, messagebox
import tkinter.simpledialog as simpledialog
import threading
import time
import queue
import re
import os
import json
import datetime
import spacy
import keyboard
import hashlib


class OverlayWindow:
    def __init__(self, username="default"):
        self.root = tk.Tk()
        self.root.grid_rowconfigure(0, weight=0)  # Controls
        self.root.grid_rowconfigure(1, weight=1)  # Live box
        self.root.grid_rowconfigure(2, weight=0)  # History label
        self.root.grid_rowconfigure(3, weight=1)  # History box
        self.root.grid_columnconfigure(0, weight=1)
        self.controls_frame = tk.Frame(self.root)
        self.controls_frame.grid(row=0, column=0, sticky="ew", pady=5)
        self.status_label = tk.Label(
            self.controls_frame, text="Ready", bg="black", fg="white", font=("Arial", 8)
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.device_label = tk.Label(
            self.controls_frame,
            text="Device: Unknown",
            bg="black",
            fg="white",
            font=("Arial", 8),
        )
        self.device_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.live_merge_text = tk.Text(
            self.root, font=("Arial", 12), wrap=tk.WORD, height=10
        )
        self.live_merge_text.grid(row=1, column=0, sticky="nsew")
        self.history_label = tk.Label(
            self.root, text="Generation History:", font=("Arial", 10)
        )
        self.history_label.grid(row=2, column=0, sticky="ew")
        self.history_text = tk.Text(
            self.root, font=("Arial", 10), wrap=tk.WORD, height=10
        )
        self.history_text.grid(row=3, column=0, sticky="nsew")
        self.live_merge_label = tk.Label(
            self.controls_frame,
            text="",
            bg="black",
            fg="yellow",
            font=("Arial", 12),
            wraplength=400,
            justify=tk.LEFT,
        )
        self.live_merge_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.llm_choice = tk.StringVar(value="ollama")
        self.ollama_radio = ttk.Radiobutton(
            self.controls_frame,
            text="Ollama (Local)",
            variable=self.llm_choice,
            value="ollama",
        )
        self.ollama_radio.pack(side=tk.LEFT, padx=5)
        self.groq_radio = ttk.Radiobutton(
            self.controls_frame,
            text="Groq (Online)",
            variable=self.llm_choice,
            value="groq",
        )
        self.groq_radio.pack(side=tk.LEFT, padx=5)
        # Finalize button
        self.finalize_button = tk.Button(
            self.controls_frame,
            text="Finalize Suggestion",
            command=self.finalize_suggestion,
            bg="green",
            fg="white",
        )
        self.finalize_button.pack(side=tk.LEFT, padx=5)
        # Pause/Resume Recording button
        self.pause_resume_button = tk.Button(
            self.controls_frame,
            text="Pause Recording",
            command=self.toggle_recording,
            bg="orange",
            fg="white",
        )
        self.pause_resume_button.pack(side=tk.LEFT, padx=5)
        # Upload button
        self.upload_button = tk.Button(
            self.controls_frame,
            text="Upload Documents",
            command=self.upload_document,
            bg="blue",
            fg="white",
        )
        self.upload_button.pack(side=tk.LEFT, padx=5)
        # Initialize attributes
        self.live_merge_str = ""
        self.is_finalizing = False
        self.last_input_time = time.time()
        self.sentence_end_time = 0
        self.sentence_timer = None
        self.live_transcript = ""
        self.speech_length = 0
        self.conversations = []
        self.context = "Meeting context: AI and ML discussions, technical questions."
        self.suggestion_cache = {}
        self.processed_transcripts = (
            set()
        )  # Track processed transcripts to avoid redundancy
        self.recent_merge_hashes = []
        self.capture = None
        self.transcriber = None
        self.reset_flag = False
        self.username = username
        # User info
        self.user_label = tk.Label(
            self.controls_frame,
            text=f"User: {self.username}",
            bg="lightblue",
            fg="black",
            font=("Arial", 10),
        )
        self.user_label.pack(side=tk.LEFT, padx=5)
        self.change_user_button = tk.Button(
            self.controls_frame,
            text="Change User",
            command=self.change_user,
            bg="lightgray",
            fg="black",
        )
        self.change_user_button.pack(side=tk.LEFT, padx=5)
        # Test speaker button
        self.test_speaker_button = tk.Button(
            self.controls_frame,
            text="Test Speaker",
            command=self.test_speaker,
            bg="yellow",
            fg="black",
        )
        self.test_speaker_button.pack(side=tk.LEFT, padx=5)

    def update_ui(self, transcript, refined, snippet, suggestion):
        self.status_label.config(text="Status: Ready", fg="blue")
        # Removed notification: window focus and beep on generation
        self.root.update()  # Force redraw
        self.root.update_idletasks()
        print(
            f"UI updated successfully with text: {self.live_merge_text.get(1.0, tk.END).strip()[:100]}..."
        )
        sys.stdout.flush()
        try:
            text = f"Transcript: {transcript}\n\nRefined: {refined}\n\nAnonymized: {snippet}\n\nSuggestion: {suggestion}"
            self.live_merge_text.delete(1.0, tk.END)  # Clear first
            self.root.update()  # Update before setting
            self.live_merge_text.insert(tk.END, text)  # Insert text
            import datetime

            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.history_text.insert(
                1.0, f"[{timestamp}]\nSuggestion: {suggestion}\n\n"
            )
            self.status_label.config(text="Status: Ready", fg="blue")
            self.root.lift()  # Bring window to front
            self.root.attributes("-topmost", True)  # Keep on top
            self.root.focus_force()  # Force focus
            self.root.bell()  # Beep to alert
            self.root.update()  # Force redraw
            self.root.update_idletasks()
            print(
                f"UI updated successfully with text: {self.live_merge_text.get(1.0, tk.END).strip()[:100]}..."
            )
            sys.stdout.flush()
        except Exception as e:
            print(f"UI update error: {e}")
            sys.stdout.flush()
            # Fallback to just suggestion
            try:
                self.live_merge_label.config(text=f"Suggestion: {suggestion}")
                self.add_to_history(suggestion)
                self.status_label.config(text="Status: Ready", fg="blue")
                self.root.lift()
                self.root.attributes("-topmost", True)
                self.root.focus_force()
                self.root.bell()
                # Dynamic resize
                self.adjust_window_size(suggestion)
                self.root.update()
                self.root.update_idletasks()
                print("Fallback UI update")
                sys.stdout.flush()
            except Exception as e2:
                print(f"Fallback UI error: {e2}")
                sys.stdout.flush()
        try:
            text = f"Transcript: {transcript}\n\nRefined: {refined}\n\nAnonymized: {snippet}\n\nSuggestion: {suggestion}"
            self.live_merge_text.delete(1.0, tk.END)
            self.live_merge_text.insert(tk.END, text)
            self.status_label.config(text="Status: Ready", fg="blue")
            self.root.lift()  # Bring window to front
            self.root.attributes("-topmost", True)  # Keep on top
            self.root.focus_force()  # Force focus
            self.root.bell()  # Beep to alert
            self.root.update()  # Force redraw
            self.root.update_idletasks()
            print(
                f"UI updated successfully with text: {self.live_merge_text.get(1.0, tk.END).strip()[:100]}..."
            )
            sys.stdout.flush()
            # Popup notification
            import tkinter.messagebox as messagebox

            messagebox.showinfo(
                "AI Meeting Copilot", "New suggestion generated! Check the window."
            )
        except Exception as e:
            print(f"UI update error: {e}")
            sys.stdout.flush()
            # Fallback to just suggestion
            try:
                self.live_merge_text.delete(1.0, tk.END)
                self.live_merge_text.insert(tk.END, f"Suggestion: {suggestion}")
                self.status_label.config(text="Status: Ready", fg="blue")
                self.root.lift()
                self.root.attributes("-topmost", True)
                self.root.focus_force()
                self.root.bell()
                self.root.update()
                self.root.update_idletasks()
                print("Fallback UI update")
                sys.stdout.flush()
            except Exception as e2:
                print(f"Fallback UI error: {e2}")
                sys.stdout.flush()
            # Fallback to just suggestion
            try:
                self.live_merge_text.delete(1.0, tk.END)
                self.live_merge_text.insert(tk.END, f"Suggestion: {suggestion}")
                self.status_label.config(text="Status: Ready", fg="blue")
                self.root.lift()
                self.root.attributes("-topmost", True)
                self.root.focus_force()
                self.root.bell()
                self.root.update()
                self.root.update_idletasks()
                print("Fallback UI update")
                sys.stdout.flush()
            except Exception as e2:
                print(f"Fallback UI error: {e2}")
                sys.stdout.flush()
            # Fallback to just suggestion
            try:
                self.live_merge_label.config(text=f"Suggestion: {suggestion}")
                self.status_label.config(text="Status: Ready", fg="blue")
                self.root.lift()
                self.root.attributes("-topmost", True)
                self.root.focus_force()
                self.root.bell()
                self.root.update()
                self.root.update_idletasks()
                print("Fallback UI update")
                sys.stdout.flush()
            except Exception as e2:
                print(f"Fallback UI error: {e2}")
                sys.stdout.flush()
        try:
            self.live_merge_label.config(
                text=f"Transcript: {transcript}\n\nRefined: {refined}\n\nAnonymized: {snippet}\n\nSuggestion: {suggestion}"
            )
            self.add_to_history(suggestion)
            self.status_label.config(text="Status: Ready", fg="blue")
            self.root.lift()  # Bring window to front
            self.root.attributes("-topmost", True)  # Keep on top
            # Dynamic resize
            self.adjust_window_size(suggestion)
            self.root.update_idletasks()
            print("UI updated successfully")
            sys.stdout.flush()
        except Exception as e:
            print(f"UI update error: {e}")
            sys.stdout.flush()
            # Fallback to just suggestion
            try:
                self.live_merge_label.config(text=f"Suggestion: {suggestion}")
                self.status_label.config(text="Status: Ready", fg="blue")
                self.root.lift()
                self.root.attributes("-topmost", True)
                print("Fallback UI update")
                sys.stdout.flush()
            except Exception as e2:
                print(f"Fallback UI error: {e2}")
                sys.stdout.flush()
        try:
            self.live_merge_label.config(
                text=f"Transcript: {transcript}\n\nRefined: {refined}\n\nAnonymized: {snippet}\n\nSuggestion: {suggestion}"
            )
            self.status_label.config(text="Status: Ready", fg="blue")
            self.root.update_idletasks()
            print("UI updated successfully")
            sys.stdout.flush()
        except Exception as e:
            print(f"UI update error: {e}")
            sys.stdout.flush()
            # Fallback to just suggestion
            try:
                self.live_merge_label.config(text=f"Suggestion: {suggestion}")
                self.status_label.config(text="Status: Ready", fg="blue")
                print("Fallback UI update")
                sys.stdout.flush()
            except Exception as e2:
                print(f"Fallback UI error: {e2}")
                sys.stdout.flush()

    def save_to_memory(self, transcript, refined, anonymized, suggestion):
        try:
            with open("record.md", "a", encoding="utf-8") as f:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                entry = f"## [{timestamp}]\n\n**Transcript:** {transcript}\n\n**Refined:** {refined}\n\n**Anonymized:** {anonymized}\n\n**Suggestion:** {suggestion}\n\n---\n\n"
                f.write(entry)
        except Exception as e:
            print(f"Error saving to record: {e}")

    def update_suggestion(self, text):
        if self.capture and self.capture.paused:
            self.live_suggestion_label.config(text=f"Suggestion: {text}")
        else:
            self.live_suggestion_label.config(text="")

    def set_capture(self, capture):
        """Set the audio capture instance for UI controls."""
        self.capture = capture
        print("Capture instance set on UI.")
        if capture:
            device_info = capture.get_device_info()
            self.device_label.config(
                text=f"Device: {device_info['name']} ({device_info['type']})"
            )

    def set_transcriber(self, transcriber):
        """Set the transcription service instance."""
        self.transcriber = transcriber
        print("Transcriber instance set on UI.")
        self.nlp = spacy.load("en_core_web_sm")  # SpaCy for semantic chunking

    def set_status(self, status):
        self.status_label.config(text=status)

    def update_live_transcript(self, transcript):
        self.live_transcript += " " + transcript
        self.live_merge_str += " " + transcript
        if transcript.strip().endswith((".", "!", "?")):
            if self.sentence_timer:
                self.root.after_cancel(self.sentence_timer)
            self.sentence_timer = self.root.after(
                5000, self.process_merged_text
            )  # Wait 5s after sentence for full speech
        self.speech_length += len(transcript.split())  # Count words
        self.last_input_time = time.time()
        # Stream in 4-word chunks
        words = self.live_merge_str.strip().split()
        if len(words) >= 4:
            chunk = " ".join(words[-4:])
            # Update live display
            self.live_merge_text.delete(1.0, tk.END)
            display_text = self.live_merge_str.strip()
            self.live_merge_text.insert(tk.END, display_text)
            self.root.after(1000, self.check_merge_inactivity)

    def process_merged_text(self):
        combined_transcript = self.live_merge_str.strip()
        import threading

        threading.Thread(
            target=self._process_in_background, args=(combined_transcript,), daemon=True
        ).start()

    def check_merge_inactivity(self):
        if self.live_merge_str and not self.is_finalizing:
            text = self.live_merge_str.strip()
            sentence_count = len(list(self.nlp(text).sents))
            if (
                len(text.split()) > 3 and time.time() - self.last_input_time > 5
            ) or sentence_count > 2:
                self.is_finalizing = True
                combined_transcript = text
                import threading

                threading.Thread(
                    target=self._process_in_background,
                    args=(combined_transcript,),
                    daemon=True,
                ).start()
        self.root.after(1000, self.check_merge_inactivity)  # Check every second

    def select_or_register_user(self):
        users_file = "data/users.txt"
        os.makedirs("data", exist_ok=True)
        if os.path.exists(users_file):
            with open(users_file, "r") as f:
                users = [line.strip() for line in f if line.strip()]
        else:
            users = []

        if users:
            # Prompt to select existing or enter new
            user_input = simpledialog.askstring(
                "User Selection",
                f"Registered users: {', '.join(users)}\nEnter username (existing or new):",
            )
        else:
            user_input = simpledialog.askstring(
                "User Registration", "No registered users. Enter a new username:"
            )

        if user_input:
            user_input = user_input.strip()
            if user_input not in users:
                users.append(user_input)
                with open(users_file, "w") as f:
                    f.write("\n".join(users))
                print(f"Registered new user: {user_input}")
            return user_input
        else:
            return "default"

    def finalize_suggestion(self):
        if self.live_merge_str and not self.is_finalizing:
            self.is_finalizing = True
            combined_transcript = self.live_merge_str.strip()
            import threading

            threading.Thread(
                target=self._process_in_background,
                args=(combined_transcript,),
                daemon=True,
            ).start()
            self.status_label.config(text="Status: Finalizing...", fg="orange")
            self.log_to_memory(
                "Action",
                "Suggestion finalized manually",
                f"Text length: {len(combined_transcript)} characters",
            )
        else:
            self.log_to_memory(
                "Action", "Finalize attempted but no text", "No merged text available"
            )

    def toggle_recording(self):
        if hasattr(self, "capture") and self.capture:
            if not self.capture.paused:
                self.capture.paused = True
                self.pause_resume_button.config(text="Resume Recording", bg="green")
                self.status_label.config(text="Status: Recording Paused", fg="red")
                print("Recording paused")
                self.log_to_memory(
                    "Action", "Recording paused", "Audio capture stopped"
                )
            else:
                self.capture.paused = False
                self.pause_resume_button.config(text="Pause Recording", bg="orange")
                self.status_label.config(text="Status: Recording Resumed", fg="blue")
                print("Recording resumed")
                self.log_to_memory(
                    "Action", "Recording resumed", "Audio capture started"
                )
        else:
            print("Capture not initialized")
            self.log_to_memory(
                "Error", "Recording toggle failed", "Capture not initialized"
            )

    def upload_document(self):
        file_path = filedialog.askopenfilename(
            title="Select Document",
            filetypes=[
                ("Text files", "*.txt"),
                ("PDF files", "*.pdf"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if file_path:
            try:
                text = ""
                if file_path.lower().endswith(".pdf"):
                    from PyPDF2 import PdfReader

                    reader = PdfReader(file_path)
                    total_pages = len(reader.pages)
                    for i, page in enumerate(reader.pages):
                        text += page.extract_text() + "\n"
                        if (i + 1) % 10 == 0:  # Progress for large PDFs
                            self.status_label.config(
                                text=f"Status: Processing page {i + 1}/{total_pages}",
                                fg="blue",
                            )
                            self.root.update()
                    details = f"PDF uploaded: {total_pages} pages extracted, {len(text)} characters."
                elif file_path.lower().endswith(".json"):
                    import json

                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Flatten JSON to text (simple recursive extraction)
                    def flatten_json(obj, prefix=""):
                        result = []
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                result.extend(
                                    flatten_json(v, f"{prefix}.{k}" if prefix else k)
                                )
                        elif isinstance(obj, list):
                            for i, item in enumerate(obj):
                                result.extend(flatten_json(item, f"{prefix}[{i}]"))
                        else:
                            result.append(f"{prefix}: {str(obj)}")
                        return result

                    text = "\n".join(flatten_json(data))
                    details = (
                        f"JSON uploaded: Parsed and flattened, {len(text)} characters."
                    )
                elif file_path.lower().endswith(".txt"):
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    details = f"Text file uploaded: {len(text)} characters."
                else:
                    messagebox.showerror(
                        "Unsupported File",
                        "Supported: .txt, .pdf, .json. For others, convert to text first.",
                    )
                    return

                if hasattr(self, "vector_store") and self.vector_store:
                    # Chunk large text to avoid memory issues
                    chunk_size = 10000  # Characters per chunk
                    chunks = [
                        text[i : i + chunk_size]
                        for i in range(0, len(text), chunk_size)
                    ]
                    for chunk in chunks:
                        self.vector_store.add_experience(chunk)
                    self.status_label.config(
                        text="Status: Document uploaded", fg="green"
                    )
                    messagebox.showinfo(
                        "Upload Successful",
                        f"Document uploaded successfully.\n{details}\nText chunked ({len(chunks)} chunks) and added to vector store.",
                    )
                    # Clear the text box
                    self.live_merge_text.delete(1.0, tk.END)
                    print(
                        f"Uploaded document: {file_path} - {details} - {len(chunks)} chunks"
                    )
                    # Log to memory.txt
                    self.log_to_memory(
                        "Upload",
                        f"Document uploaded: {file_path.split('/')[-1]}",
                        f"Type: {file_path.split('.')[-1]}, Details: {details}, Chunks: {len(chunks)}",
                    )
                else:
                    messagebox.showerror("Error", "Vector store not available.")
            except Exception as e:
                print(f"Error uploading document: {e}")
                messagebox.showerror("Upload Failed", f"Error: {str(e)}")
                self.status_label.config(text="Status: Upload failed", fg="red")
                # Log error
                self.log_to_memory(
                    "Error",
                    "Document upload failed",
                    f"File: {file_path}, Error: {str(e)}",
                )

    def change_user(self):
        # Prompt for new user
        users_file = "data/users.txt"
        if os.path.exists(users_file):
            with open(users_file, "r") as f:
                users = [line.strip() for line in f if line.strip()]
        else:
            users = []

        root = tk.Tk()
        root.withdraw()
        if users:
            user_input = simpledialog.askstring(
                "Change User",
                f"Registered users: {', '.join(users)}\nEnter username (existing or new):",
                parent=root,
            )
        else:
            user_input = simpledialog.askstring(
                "Change User", "No registered users. Enter a new username:", parent=root
            )
        root.destroy()

        if user_input:
            user_input = user_input.strip()
            if user_input not in users:
                users.append(user_input)
                with open(users_file, "w") as f:
                    f.write("\n".join(users))
                print(f"Registered new user: {user_input}")
            # Update config
            config_file = "data/user_config.txt"
            with open(config_file, "w") as f:
                f.write(user_input)
            # Reload vector store
            self.vector_store = LocalVectorStore(user_input)
            self.vector_store.load_documents()
            # Update UI
            self.username = user_input
            self.user_label.config(text=f"User: {self.username}")
            messagebox.showinfo(
                "User Changed", f"User changed to {user_input}. Vector store reloaded."
            )
            self.log_to_memory(
                "Action",
                "User changed",
                f"New user: {user_input}, vector store reloaded",
            )
        else:
            messagebox.showinfo("No Change", "User change cancelled.")

    def test_speaker(self):
        try:
            import winsound

            winsound.Beep(800, 500)  # Frequency 800Hz, duration 500ms
            messagebox.showinfo(
                "Test Speaker", "Beep played successfully. Speaker is working."
            )
        except Exception as e:
            messagebox.showerror("Test Speaker Failed", f"Error: {str(e)}")
            self.log_to_memory("Error", "Speaker test failed", f"Error: {str(e)}")

    def log_to_memory(self, category, content, details):
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{timestamp} | [{category}] | {content} | Details: {details}\n"
        try:
            with open("memory.txt", "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            print(f"Failed to log to memory.txt: {e}")

    def _process_in_background(self, combined_transcript):
        print(f"Processing merged text: {combined_transcript}")
        sys.stdout.flush()
        use_ollama = self.llm_choice.get() == "ollama"
        try:
            refined_transcript = refine_transcript(
                combined_transcript, use_ollama=use_ollama
            )
        except Exception as e:
            print(f"Refinement error: {e}, using original")
            refined_transcript = combined_transcript
        print(f"Refined: {refined_transcript}")
        sys.stdout.flush()
        snippet = anonymize_text(refined_transcript)
        print(f"Anonymized: {snippet}")
        sys.stdout.flush()
        # Use pre-loaded context for better personalization
        context = self.context
        print("Context loaded.")
        sys.stdout.flush()
        # Check cache for suggestion
        import hashlib

        cache_key = hashlib.md5(f"{snippet}_{context[:300]}".encode()).hexdigest()
        if cache_key in self.suggestion_cache:
            suggestion = self.suggestion_cache[cache_key]
            print("Suggestion loaded from cache.")
            sys.stdout.flush()
        else:
            suggestion = generate_suggestion(context, snippet, use_ollama=use_ollama)
            self.suggestion_cache[cache_key] = suggestion
            print("Suggestion generated and cached.")
            sys.stdout.flush()
        print("Suggestion generated.")  # Avoid Unicode issues
        sys.stdout.flush()
        # Update UI with results (thread-safe)
        self.root.after(
            0, lambda: self.live_merge_label.config(text=f"Suggestion: {suggestion}")
        )
        self.root.after(
            0, lambda: self.status_label.config(text="Status: Ready", fg="blue")
        )
        # Save to memory
        self.save_to_memory(
            combined_transcript, refined_transcript, snippet, suggestion
        )
        # Add to recent hashes
        current_hash = hashlib.md5(combined_transcript.encode()).hexdigest()
        self.recent_merge_hashes.append(current_hash)
        if len(self.recent_merge_hashes) > 10:
            self.recent_merge_hashes.pop(0)
        # Clear live transcript after processing, but keep merge for continuous streaming
        self.live_transcript = ""
        # self.live_merge_text = ""  # Keep for streaming
        # self.live_merge_label.config(text="")  # Keep for streaming
        self.speech_length = 0
        self.is_finalizing = False  # Reset flag after processing
        self.set_status("Ready")

    def update_display(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, "AI Meeting Copilot - Live Transcript\n\n")
        if self.live_merge_str:
            self.text.insert(tk.END, f"Live: {self.live_merge_str.strip()}\n\n")
        self.text.insert(tk.END, "Recent Conversations\n\n")
        for ts, trans, ref, anon, sugg in reversed(self.conversations):  # Recent first
            self.text.insert(tk.END, "Transcription: ", "transcription")
            self.text.insert(tk.END, f"{trans}\n", "transcription")
            self.text.insert(tk.END, "Transcribe: ", "transcribe")
            self.text.insert(tk.END, f"{ref}\n", "transcribe")
            self.text.insert(tk.END, "Refine: ", "refine")
            self.text.insert(tk.END, f"{anon}\n", "refine")
            self.text.insert(tk.END, "Suggestion: ", "suggestion")
            self.text.insert(tk.END, f"{sugg}\n\n", "suggestion")
        if not self.conversations:
            self.text.insert(tk.END, "Waiting for suggestions...")
        self.text.config(state=tk.DISABLED)
        self.root.lift()
        self.root.focus_force()
        self.root.update_idletasks()
        self.root.update()

    def toggle_visibility(self):
        if self.visible:
            self.root.withdraw()
            self.visible = False
        else:
            self.root.deiconify()
            self.visible = True

    def run(self):
        self.check_merge_inactivity()  # Start inactivity check
        self.root.mainloop()


def main():
    print("Main started")
    sys.stdout.flush()

    # User selection with config
    config_file = "data/user_config.txt"
    users_file = "data/users.txt"
    os.makedirs("data", exist_ok=True)

    # Check for last user
    last_user = None
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            last_user = f.read().strip()

    if last_user:
        username = last_user
        print(f"Using last user: {username}")
    else:
        if os.path.exists(users_file):
            with open(users_file, "r") as f:
                users = [line.strip() for line in f if line.strip()]
        else:
            users = []

        root = tk.Tk()
        root.withdraw()  # Hide main window
        if users:
            user_input = simpledialog.askstring(
                "User Selection",
                f"Registered users: {', '.join(users)}\nEnter username (existing or new):",
                parent=root,
            )
        else:
            user_input = simpledialog.askstring(
                "User Registration",
                "No registered users. Enter a new username:",
                parent=root,
            )
        root.destroy()

        if user_input:
            user_input = user_input.strip()
            if user_input not in users:
                users.append(user_input)
                with open(users_file, "w") as f:
                    f.write("\n".join(users))
                print(f"Registered new user: {user_input}")
            username = user_input
            # Save as last user
            with open(config_file, "w") as f:
                f.write(username)
        else:
            username = "default"

    # Initialize components
    print("Before vector_store")
    sys.stdout.flush()
    vector_store = LocalVectorStore(username)
    print("Vector store created")
    sys.stdout.flush()
    vector_store.load_documents()
    vector_store.add_meeting_transcripts()
    vector_store.add_project_docs()
    print("Documents loaded")
    sys.stdout.flush()

    window = OverlayWindow(username)
    window.vector_store = vector_store
    print("Vector store set on UI.")
    print("Window created")
    sys.stdout.flush()

    print("Before capture")
    sys.stdout.flush()
    capture = AudioCapture()
    print("Capture created")
    sys.stdout.flush()
    capture.start_capture()
    print("Capture started")
    sys.stdout.flush()

    # Set capture on window
    window.set_capture(capture)

    print("Before transcriber")
    sys.stdout.flush()
    transcriber = TranscriptionService()
    print("Transcriber created")
    sys.stdout.flush()
    transcriber.start_transcription()
    print("Transcription started")
    sys.stdout.flush()

    # Set transcriber on window
    window.set_transcriber(transcriber)

    last_transcript = ""
    full_speech = []
    silence_counter = 0

    # Audio feeding thread
    def feed_audio():
        while True:
            chunk = capture.get_audio_chunk()
            if chunk:
                transcriber.add_audio_chunk(chunk)
            time.sleep(0.01)

    audio_thread = threading.Thread(target=feed_audio, daemon=True)
    audio_thread.start()

    # Hotkey listener
    def on_activate():
        window.toggle_visibility()

    def on_pause():
        window.pause_recording()

    keyboard.add_hotkey("ctrl+shift+g", on_activate)
    keyboard.add_hotkey("ctrl+shift+p", on_pause)

    # Timer for processing
    def process():
        nonlocal last_transcript, full_speech, silence_counter
        if window.reset_flag:
            full_speech = []
            silence_counter = 0
            window.reset_flag = False
        print("Process called")
        sys.stdout.flush()
        transcript = transcriber.get_transcript()
        if transcript and transcript != last_transcript and not capture.paused:
            print(f"New transcript: {transcript}")
            sys.stdout.flush()
            last_transcript = transcript
            full_speech.append(transcript)
            window.update_live_transcript(transcript)
            window.set_status("Listening...")
            silence_counter = 0
        else:
            silence_counter += 1
            if silence_counter > 2:
                window.set_status("Ready")

        # Disabled partial processing; only process finalized live merge text in process_merged_text
        window.root.after(1000, process)  # Schedule next check

    window.root.after(1000, process)  # Start the timer
    print("After scheduled, starting mainloop")
    sys.stdout.flush()
    window.run()


if __name__ == "__main__":
    main()
