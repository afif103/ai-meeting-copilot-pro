"""
Enhanced Transcription Service - Production Ready
Features:
- Optimized Whisper model with GPU acceleration
- Smart audio buffering with overlap
- Voice Activity Detection (VAD)
- Post-processing for technical terms
- Automatic error recovery
- Performance monitoring
"""

from faster_whisper import WhisperModel
import numpy as np
import threading
import queue
import time
import webrtcvad
import os


class TranscriptionService:
    """Production-grade transcription service with advanced features"""

    def __init__(self, model_size="small"):
        """
        Initialize transcription service

        Args:
            model_size: Whisper model size ("tiny", "base", "small", "medium", "large")
        """
        # Auto-detect best device (GPU if available, else CPU)
        device = os.getenv("WHISPER_DEVICE", "cuda")
        compute_type = "int8"  # Good balance of speed and accuracy

        print(f"Loading Whisper model: {model_size} on {device}...")

        try:
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                num_workers=4,  # Parallel processing
                download_root=None,  # Use default cache
            )
            print(f"[OK] Whisper model loaded successfully on {device}")
        except Exception as e:
            print(f"[WARN] GPU failed ({e}), falling back to CPU...")
            try:
                self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
                print(f"[OK] Whisper model loaded on CPU")
            except Exception as e2:
                print(f"[ERROR] Fatal: Could not load Whisper model: {e2}")
                raise

        # Queues and buffers
        self.transcript_queue = queue.Queue()
        self.audio_buffer = []

        # State
        self.is_transcribing = False

        # VAD for speech detection
        self.vad = webrtcvad.Vad(1)  # Aggressiveness: 0 (least) to 3 (most)
        self.vad_threshold = 0.5

        # Smart buffering parameters
        self.max_buffer_size = 1920000  # 120 seconds at 16kHz
        self.min_chunk_size = 192000  # 12 seconds minimum
        self.overlap_size = 96000  # 6 seconds overlap for context

        # Performance tracking
        self.transcription_count = 0
        self.last_transcription_time = 0
        self.total_processing_time = 0

        print("[OK] Transcription service initialized")

    def post_process_transcript(self, text):
        """
        Post-process transcript with smart corrections
        Fixes common speech-to-text errors, especially technical terms

        Args:
            text: Raw transcript text

        Returns:
            Corrected text
        """
        if not text:
            return text

        # Technical term corrections (case-insensitive)
        corrections = {
            # AI/ML terms
            "check pointing": "checkpointing",
            "variance": "VRAM",
            "v ram": "VRAM",
            "lorry": "LoRA",
            "lora": "LoRA",
            "hundred": "H100",
            "a hundred": "A100",
            "0.3": "ZeRO-3",
            "zero 3": "ZeRO-3",
            "zero three": "ZeRO-3",
            "atom": "Adam",
            "atom optimizer": "Adam optimizer",
            # Frameworks
            "pytorch": "PyTorch",
            "pie torch": "PyTorch",
            "tensor flow": "TensorFlow",
            "ten sir flow": "TensorFlow",
            # Hardware
            "cuda": "CUDA",
            "gpu": "GPU",
            "gpus": "GPUs",
            "cpu": "CPU",
            "cpus": "CPUs",
            "nvidia": "NVIDIA",
            # Common terms
            "api": "API",
            "apis": "APIs",
            "ml": "ML",
            "ai": "AI",
            "ui": "UI",
            "ux": "UX",
            # Metrics
            "tokens per sec": "tokens/sec",
            "tokens per second": "tokens/sec",
            "milliseconds": "ms",
            "milli seconds": "ms",
            # Technical phrases
            "dot product": "dot-product",
            "back prop": "backprop",
            "back propagation": "backpropagation",
            "gradient descent": "gradient descent",
            "fine tuning": "fine-tuning",
            "fine tune": "fine-tune",
            # Code-related
            "eval": "eval()",
            "accumulation": "gradient accumulation",
            "offloading": "offloading",
            "watch flag": "launch flag",
            # Specific fixes
            "new lovelow waits-gaussian": "init_lora_weights='gaussian'",
            "load optimization true": "offload_optimizer_state=True",
        }

        # Apply corrections (case-insensitive)
        import re

        result = text

        for wrong, correct in corrections.items():
            # Create case-insensitive pattern
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            result = pattern.sub(correct, result)

        # Clean up extra whitespace
        result = " ".join(result.split())

        return result

    def start_transcription(self):
        """Start the transcription service in background thread"""
        print("[MIC] Starting transcription service...")
        self.is_transcribing = True

        # Start transcription loop in daemon thread
        transcription_thread = threading.Thread(
            target=self._transcription_loop, daemon=True, name="TranscriptionLoop"
        )
        transcription_thread.start()

        print("[OK] Transcription service running")

    def add_audio_chunk(self, audio_data):
        """
        Add audio chunk to buffer with preprocessing

        Args:
            audio_data: Audio data as bytes (int16)
        """
        try:
            # Convert bytes to numpy float32 array
            audio_np = np.frombuffer(audio_data, np.int16).astype(np.float32) / 32768.0

            # Amplify volume (helps with quiet audio)
            audio_np *= 5.0

            # Clip to prevent distortion
            audio_np = np.clip(audio_np, -1.0, 1.0)

            # Add to buffer
            self.audio_buffer.extend(audio_np)

            # Prevent buffer overflow (keep last max_buffer_size * 2 samples)
            if len(self.audio_buffer) > self.max_buffer_size * 2:
                self.audio_buffer = self.audio_buffer[-self.max_buffer_size :]
                print("[WARN] Buffer overflow prevented, trimmed to max size")

        except Exception as e:
            print(f"[WARN] Error adding audio chunk: {e}")

    def has_speech(self, audio_np):
        """
        Detect if audio contains speech using VAD

        Args:
            audio_np: Audio as numpy array (float32)

        Returns:
            True if speech detected, False otherwise
        """
        try:
            # Convert to int16 for VAD
            audio_int16 = (audio_np * 32767).astype(np.int16)

            # Frame length: 10ms = 160 samples at 16kHz
            frame_length = 160
            num_frames = len(audio_int16) // frame_length

            if num_frames == 0:
                return False

            speech_frames = 0

            # Check each frame
            for i in range(num_frames):
                frame = audio_int16[i * frame_length : (i + 1) * frame_length]

                if len(frame) == frame_length:
                    try:
                        if self.vad.is_speech(frame.tobytes(), 16000):
                            speech_frames += 1
                    except Exception:
                        pass  # Skip problematic frames

            # Require at least 5% speech frames
            speech_ratio = speech_frames / num_frames if num_frames > 0 else 0
            has_speech = speech_ratio > 0.05

            if has_speech:
                print(f"[SPEECH] Speech detected: {speech_ratio * 100:.1f}% of frames")

            return has_speech

        except Exception as e:
            print(f"[WARN] VAD error: {e}")
            return True  # Assume speech on error (fail-safe)

    def _transcription_loop(self):
        """Main transcription loop (runs in background thread)"""
        print("[LOOP] Transcription loop started")

        while self.is_transcribing:
            try:
                # Manage buffer size
                if len(self.audio_buffer) > self.max_buffer_size:
                    self.audio_buffer = self.audio_buffer[-self.max_buffer_size :]

                # Check if we have enough audio to transcribe
                if len(self.audio_buffer) >= self.min_chunk_size:
                    audio = np.array(self.audio_buffer)

                    # Check for speech activity
                    if self.has_speech(audio):
                        # Transcribe the audio
                        transcript = self._transcribe_audio(audio)

                        if transcript:
                            # Post-process
                            transcript = self.post_process_transcript(transcript)

                            if transcript:
                                # Add to queue
                                self.transcript_queue.put(transcript)
                                print(
                                    f"[TRANSCRIPT] Transcribed: {transcript[:100]}..."
                                )

                                # Update stats
                                self.transcription_count += 1
                                self.last_transcription_time = time.time()

                        # Keep overlap for context continuity
                        self.audio_buffer = self.audio_buffer[-self.overlap_size :]
                    else:
                        # No speech, keep some buffer for continuity
                        self.audio_buffer = self.audio_buffer[-self.overlap_size :]

                # Check every second
                time.sleep(1.0)

            except Exception as e:
                print(f"[ERROR] Transcription loop error: {e}")
                import traceback

                traceback.print_exc()
                time.sleep(2.0)  # Wait before retrying

        print("[STOP] Transcription loop stopped")

    def _transcribe_audio(self, audio):
        """
        Transcribe audio using Whisper with optimized parameters

        Args:
            audio: Audio as numpy array (float32)

        Returns:
            Transcribed text or None
        """
        try:
            start_time = time.time()

            # Transcribe with optimized parameters
            segments, info = self.model.transcribe(
                audio,
                language="en",  # Specify language for better accuracy
                vad_filter=True,  # Use VAD to filter non-speech
                vad_parameters=dict(
                    threshold=0.1,  # Low threshold for sensitivity
                    min_speech_duration_ms=250,  # Minimum speech duration
                    min_silence_duration_ms=500,  # Minimum silence to split
                ),
                beam_size=3,  # Balance speed vs accuracy
                best_of=3,  # Consider top 3 candidates
                temperature=0.0,  # Deterministic output
                compression_ratio_threshold=2.4,
                log_prob_threshold=-1.0,
                no_speech_threshold=0.6,
                condition_on_previous_text=True,  # Use context
            )

            # Collect all segments
            transcript = " ".join([segment.text for segment in segments]).strip()

            elapsed = time.time() - start_time
            self.total_processing_time += elapsed

            if transcript:
                print(f"[FAST] Transcribed in {elapsed:.2f}s: {len(transcript)} chars")

            return transcript

        except Exception as e:
            print(f"[ERROR] Transcription error: {e}")
            import traceback

            traceback.print_exc()
            return None

    def get_transcript(self):
        """
        Get next transcript from queue (non-blocking)

        Returns:
            Transcript text or None if queue is empty
        """
        try:
            return self.transcript_queue.get_nowait()
        except queue.Empty:
            return None

    def stop_transcription(self):
        """Stop the transcription service"""
        print("[STOP] Stopping transcription service...")
        self.is_transcribing = False
        time.sleep(1)  # Give thread time to finish
        print("[OK] Transcription service stopped")

    def get_stats(self):
        """
        Get transcription statistics

        Returns:
            Dictionary with statistics
        """
        return {
            "transcription_count": self.transcription_count,
            "buffer_size": len(self.audio_buffer),
            "buffer_seconds": len(self.audio_buffer) / 16000,
            "queue_size": self.transcript_queue.qsize(),
            "is_transcribing": self.is_transcribing,
            "last_transcription": self.last_transcription_time,
            "avg_processing_time": (
                self.total_processing_time / self.transcription_count
                if self.transcription_count > 0
                else 0
            ),
        }

    def clear_buffer(self):
        """Clear the audio buffer"""
        self.audio_buffer = []
        print("[CLEAR] Audio buffer cleared")

    def clear_queue(self):
        """Clear the transcript queue"""
        while not self.transcript_queue.empty():
            try:
                self.transcript_queue.get_nowait()
            except queue.Empty:
                break
        print("[CLEAR] Transcript queue cleared")


# Convenience function for testing
def test_transcription_service():
    """Test the transcription service"""
    print("[TEST] Testing TranscriptionService...\n")

    # Create service
    transcriber = TranscriptionService(model_size="small")
    transcriber.start_transcription()

    # Simulate audio (1 second of random noise)
    print("[SIM] Simulating audio input...")
    sample_rate = 16000
    duration = 1  # second

    # Generate random audio (simulates background noise)
    dummy_audio = np.random.randn(sample_rate * duration).astype(np.float32) * 0.1

    # Add in small chunks (simulates real-time audio)
    chunk_size = 800  # ~50ms chunks
    num_chunks = len(dummy_audio) // chunk_size

    for i in range(num_chunks):
        chunk = dummy_audio[i * chunk_size : (i + 1) * chunk_size]
        chunk_bytes = (chunk * 32767).astype(np.int16).tobytes()
        transcriber.add_audio_chunk(chunk_bytes)
        time.sleep(0.05)  # Simulate real-time

    print("[WAIT] Waiting for transcription (15 seconds)...")
    time.sleep(15)

    # Check for transcripts
    transcript = transcriber.get_transcript()
    if transcript:
        print(f"[OK] Got transcript: {transcript}")
    else:
        print("[INFO] No transcript (expected for random noise)")

    # Show stats
    print("\n[STATS] Statistics:")
    stats = transcriber.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    # Cleanup
    transcriber.stop_transcription()
    print("\n[OK] Test complete")


if __name__ == "__main__":
    test_transcription_service()
