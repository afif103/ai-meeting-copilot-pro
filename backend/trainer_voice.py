"""
Trainer voice-answer controller (Packet 8B).

A headless, fully-injectable state machine for the Interview Trainer's
"record a spoken answer -> transcribe it locally -> show the transcript"
flow. It contains NO Tkinter and NO hard dependency on the audio/Whisper
stack (those are injected), so the whole lifecycle is unit-testable with
fakes - no real microphone, Whisper model, profile, or network.

Responsibilities:
- single-recording guard (only one recording at a time);
- a maximum recording duration (default 120s) with a safe auto-stop;
- run transcription OFF the caller's thread; the injected `schedule(fn)`
  only does a THREAD-SAFE enqueue. The UI's design is:
      worker/timer thread -> thread-safe callback queue
                          -> a Tk MAIN-THREAD poller drains and runs them.
  No Tkinter is ever touched from a worker/timer thread;
- a generation token so a stale/cancelled worker result can never update a
  reopened or switched-profile Trainer;
- temporary WAV lifecycle: created only for transcription, deleted on
  EVERY exit path (success, empty, error, write-failure, cancel, close);
- cancellation/cleanup on window close or profile switch.

The UI injects: a recorder factory, a local transcribe function
(wav_path -> text|None), a `schedule(fn)` callback enqueue (thread-safe;
a main-thread poller runs the callbacks), and an `on_state(state, info)`
callback (always invoked on the Tk main thread).

Production helpers (MicRecorder, mic_available, make_transcribe_fn) reuse
backend.audio_capture / backend.transcription WITHOUT modifying them, and
lazy-import them so this module stays importable in a headless test env.

Stdlib only (plus the injected pieces).
"""

import os
import tempfile
import threading
import time
import wave

# Lifecycle states
READY = "ready"
RECORDING = "recording"
TRANSCRIBING = "transcribing"
CLOSED = "closed"

_SAMPLE_RATE = 16000


def _default_spawn(fn):
    threading.Thread(target=fn, daemon=True).start()


def _default_timer(delay, fn):
    return threading.Timer(delay, fn)


def _safe_remove(path):
    """Best-effort delete of a temp file; tolerates an absent file. Used by
    both WAV write-failure cleanup and normal worker cleanup so a temporary
    answer recording never lingers."""
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


class TrainerVoiceController:
    """Record -> temp WAV -> local transcribe, with cancellation safety."""

    def __init__(self, recorder_factory, transcribe_fn, schedule, on_state,
                 *, max_seconds=120, temp_dir=None, spawn=None,
                 timer_factory=None):
        self._recorder_factory = recorder_factory   # () -> recorder
        self._transcribe = transcribe_fn             # (wav_path) -> str|None
        self._schedule = schedule                    # (fn) -> run on UI thread
        self._on_state = on_state                    # (state, info) UI thread
        self._max_seconds = max_seconds
        self._temp_dir = temp_dir or tempfile.gettempdir()
        self._spawn = spawn or _default_spawn
        self._timer_factory = timer_factory or _default_timer

        self._lock = threading.RLock()
        self._state = READY
        self._gen = 0           # bumped on start AND on cancel/close
        self._recorder = None
        self._timer = None
        self._question_id = None
        self._transcript = ""
        self._closed = False

    # ---- read-only introspection (safe from any thread) ----
    @property
    def state(self):
        return self._state

    @property
    def transcript(self):
        return self._transcript

    @property
    def question_id(self):
        return self._question_id

    @property
    def is_busy(self):
        return self._state in (RECORDING, TRANSCRIBING)

    # ---- commands (called on the UI thread) ----
    def start(self, question_id):
        """Begin exactly one microphone recording. Returns True if started.
        Fails closed (no worker thread) if a recording already exists or the
        microphone cannot start."""
        with self._lock:
            if self._closed or self._state != READY:
                return False
            self._gen += 1
            gen = self._gen
            try:
                recorder = self._recorder_factory()
                recorder.start()
            except Exception:
                # mic unavailable / failed: stay READY, tell the UI
                self._emit(READY, {"status": "mic_unavailable"})
                return False
            self._recorder = recorder
            self._question_id = question_id
            self._transcript = ""
            self._state = RECORDING
            self._timer = self._timer_factory(
                self._max_seconds,
                lambda: self._schedule(lambda: self._on_cap(gen)))
            self._timer.start()
            device = getattr(recorder, "device_name", "microphone")
        self._emit(RECORDING, {"device_name": device,
                               "question_id": question_id})
        return True

    def _on_cap(self, gen):
        """Recording-limit reached (marshalled to the UI thread)."""
        with self._lock:
            if self._closed or gen != self._gen or self._state != RECORDING:
                return
        self.stop(limit_reached=True)

    def stop(self, *, limit_reached=False):
        """Stop capture and start local transcription off-thread.

        Called on the Tk main thread. A microphone/device failure in
        recorder.stop() is a recording ERROR (not no-speech): we skip the
        WAV and the transcriber and finish directly through the error
        path. The Trainer stays usable for another attempt."""
        with self._lock:
            if self._state != RECORDING:
                return False
            gen = self._gen
            recorder = self._recorder
            self._recorder = None
            self._state = TRANSCRIBING
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        try:
            audio = recorder.stop()
        except Exception:
            # device failure -> neutral error, no WAV, no transcriber, no
            # 'empty'. stop() is on the main thread, so _finish is Tk-safe.
            self._finish(gen, None, True, limit_reached)
            return True
        self._emit(TRANSCRIBING, {"limit_reached": limit_reached})
        self._spawn(lambda: self._transcribe_worker(gen, audio, limit_reached))
        return True

    def _current(self, gen):
        """True only while THIS work is still the active, in-progress
        transcription (same generation, still TRANSCRIBING, not closed)."""
        with self._lock:
            return (not self._closed and gen == self._gen
                    and self._state == TRANSCRIBING)

    def _transcribe_worker(self, gen, audio, limit_reached):
        """Runs on a worker thread. Bails out completely - no temp WAV, no
        Whisper call, no UI callback - if the recording was cancelled,
        closed, or profile-switched before or during the work; the captured
        audio is simply discarded. Empty captured audio is reported as
        no-speech WITHOUT writing a WAV or calling Whisper. A temp WAV, once
        written, is always deleted (the local Whisper call is not forcibly
        interruptible, so a late-cancelled call is allowed to return and its
        result is discarded without delivery)."""
        if not self._current(gen):
            return  # cancelled/closed before we began -> discard audio
        if not audio:
            # Correction 3: empty capture -> no-speech path, no WAV/Whisper
            self._schedule(lambda: self._finish(gen, "", False, limit_reached))
            return
        text, error, wav_path = None, False, None
        try:
            wav_path = self._write_temp_wav(audio)
            if not self._current(gen):
                return  # cancelled while writing the WAV (finally cleans up)
            text = self._transcribe(wav_path)
        except Exception:
            error = True
        finally:
            _safe_remove(wav_path)           # normal cleanup (never leaks)
        if not self._current(gen):
            return  # cancelled while Whisper ran -> discard, no UI callback
        self._schedule(lambda: self._finish(gen, text, error, limit_reached))

    def _finish(self, gen, text, error, limit_reached):
        """Apply a transcription result on the UI thread; stale/cancelled
        results (gen mismatch or closed) are ignored."""
        with self._lock:
            if self._closed or gen != self._gen or self._state != TRANSCRIBING:
                return
            self._state = READY
            if error:
                self._emit(READY, {"status": "error"})
                return
            text = (text or "").strip()
            if not text:
                self._emit(READY, {"status": "empty",
                                   "limit_reached": limit_reached})
                return
            self._transcript = text
            qid = self._question_id
        self._emit(READY, {"status": "ok", "transcript": text,
                           "question_id": qid, "limit_reached": limit_reached})

    def clear(self):
        """Drop the current transcript (only when not busy)."""
        with self._lock:
            if self.is_busy:
                return False
            self._transcript = ""
            self._question_id = None
        self._emit(READY, {"status": "cleared"})
        return True

    def cancel(self):
        """Stop any active recording/transcription and drop pending results.
        Safe to call repeatedly and from window-close / profile-switch."""
        with self._lock:
            self._gen += 1  # invalidate any in-flight worker result
            recorder = self._recorder
            self._recorder = None
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if not self._closed:
                self._state = READY
            self._transcript = ""
            self._question_id = None
        if recorder is not None:
            try:
                recorder.stop()
            except Exception:
                pass

    def close(self):
        """Permanent shutdown: cancel work and reject all future results."""
        self.cancel()
        with self._lock:
            self._closed = True
            self._state = CLOSED

    # ---- internals ----
    def _emit(self, state, info):
        self._on_state(state, info)

    def _write_temp_wav(self, audio):
        # mkstemp creates the file immediately; keep its path so we can
        # delete it if ANY write stage fails (otherwise the file leaks).
        fd, path = tempfile.mkstemp(prefix="trainer_ans_", suffix=".wav",
                                    dir=self._temp_dir)
        os.close(fd)
        try:
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)            # int16
                wf.setframerate(_SAMPLE_RATE)
                wf.writeframes(audio or b"")
        except Exception:
            _safe_remove(path)               # never leak the temp file
            raise
        return path


# ---------------------------------------------------------------------------
# Production adapters (reuse the existing audio/Whisper stack; lazy imports
# keep this module headless-importable for tests).
# ---------------------------------------------------------------------------

# Virtual / loopback / mixed inputs that must NEVER be used to record a
# spoken answer (they may carry system + interviewer audio). Rami's setup
# routes interview/system audio through Voicemeeter, so the Trainer must
# reject these and use a PHYSICAL microphone only, failing closed otherwise.
# This never touches the live-copilot "system" capture flow.
_VIRTUAL_INPUT_HINTS = (
    "voicemeeter", "vb-audio", "vb audio", "vb-cable", "cable",
    "loopback", "stereo mix", "what u hear", "wave out", "virtual", "vac",
)


def _is_virtual_input(name):
    n = (name or "").lower()
    return any(hint in n for hint in _VIRTUAL_INPUT_HINTS)


class MicRecorder:
    """Physical-microphone-only recorder backed by a fresh AudioCapture in
    mic mode. Accumulates int16 bytes; stop() returns the full recording.
    Rejects (fails closed) when the only selectable input is a Voicemeeter /
    virtual-cable / loopback device, so a spoken answer is never recorded
    from a mixed system source. Never used in tests (a fake is injected)."""

    def __init__(self):
        self._cap = None
        self._buf = bytearray()
        self._stop = threading.Event()
        self._thread = None
        self.device_name = "microphone"

    def start(self):
        try:
            from backend.audio_capture import AudioCapture
        except ImportError:
            from audio_capture import AudioCapture
        self._cap = AudioCapture(audio_source="microphone")
        self._cap.start_capture()
        info = self._cap.get_device_info() or {}
        name = info.get("name")
        if name in (None, "Error", "Unknown") or _is_virtual_input(name):
            try:
                self._cap.stop_capture()
            except Exception:
                pass
            raise RuntimeError("no physical microphone available")
        self.device_name = name
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self):
        while not self._stop.is_set():
            chunk = self._cap.get_audio_chunk()
            if chunk:
                self._buf.extend(chunk)
            else:
                time.sleep(0.02)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._cap is not None:
            try:
                self._cap.stop_capture()
            except Exception:
                pass
        return bytes(self._buf)


def mic_available():
    """True only if a PHYSICAL input microphone is selectable. Probes the
    existing AudioCapture mic-mode selection without opening a stream and
    REJECTS Voicemeeter / virtual-cable / loopback devices, so the Trainer
    never silently records mixed system+interviewer audio. Returns False on
    any error (fail closed)."""
    try:
        try:
            from backend.audio_capture import AudioCapture
        except ImportError:
            from audio_capture import AudioCapture
        cap = AudioCapture(audio_source="microphone")
        try:
            idx = cap._select_best_device()
            if idx is None:
                return False
            name = cap.p.get_device_info_by_index(idx).get("name", "")
            return not _is_virtual_input(name)
        finally:
            try:
                cap.p.terminate()
            except Exception:
                pass
    except Exception:
        return False


def make_transcribe_fn(get_transcriber):
    """Build a (wav_path -> text) function that reuses the application's
    already-loaded TranscriptionService (the existing local Faster-Whisper
    path). `get_transcriber` is called at transcribe time so a still-loading
    service is handled (raises -> the controller reports a neutral error).

    The production `_transcribe_audio()` returns None for BOTH genuine
    silence and an internal model failure, which the controller cannot tell
    apart. So we use the existing local VAD `has_speech()` to disambiguate:
      * no speech detected            -> return "" (UI: 'No speech detected');
      * speech present but no text    -> raise (UI: neutral error/try again);
      * text produced                 -> return it.
    A transcriber double without `has_speech` falls back to assuming speech
    is present (an empty transcript is then treated as a failure, not as
    silence). No cloud transcription and no second model are introduced."""

    def _transcribe(wav_path):
        transcriber = get_transcriber()
        if transcriber is None:
            raise RuntimeError("local transcription not ready")
        import numpy as np
        with wave.open(wav_path, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, np.int16).astype(np.float32) / 32768.0

        has_speech = getattr(transcriber, "has_speech", None)
        if callable(has_speech):
            try:
                speech = bool(has_speech(audio))
            except Exception:
                speech = True            # safe fallback: let transcribe decide
        else:
            speech = True                # double without has_speech: assume
        if not speech:
            return ""                    # genuine silence -> 'No speech detected'

        text = transcriber._transcribe_audio(audio)
        if not text:
            # speech was present but the local model failed/returned nothing
            raise RuntimeError("local transcription failed")
        return text

    return _transcribe
