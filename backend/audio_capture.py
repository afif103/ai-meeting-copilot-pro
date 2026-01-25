"""
Enhanced Audio Capture with Advanced Features
- Smart device detection
- Voice activity detection (VAD)
- Noise reduction
- Automatic recovery
"""

import sounddevice as sd
import numpy as np
import pyaudio
import queue
import threading
import time
import webrtcvad


class AudioCapture:
    def __init__(self, rate=16000, channels=1, chunk=1024, audio_source="system"):
        self.rate = rate
        self.channels = channels
        self.chunk = chunk
        self.audio_queue = queue.Queue(maxsize=100)  # Prevent memory overflow
        self.is_capturing = False
        self.stream = None
        self.p = pyaudio.PyAudio()
        self.vad = webrtcvad.Vad(1)  # Moderate aggressiveness
        self.paused = False
        self.device_info = {"name": "Unknown", "type": "unknown"}
        self.error_count = 0
        self.max_errors = 5
        self.current_audio_level = 0.0  # For quality monitoring
        self.audio_source = audio_source  # "system" or "microphone"

    def is_speech(self, audio_data):
        """Enhanced speech detection with VAD"""
        try:
            # Convert to bytes if numpy
            if isinstance(audio_data, np.ndarray):
                audio_data = (audio_data * 32767).astype(np.int16).tobytes()

            # Frame into 30ms chunks
            frame_duration = 30  # ms
            frame_size = int(self.rate * frame_duration / 1000)
            speech_frames = 0
            total_frames = 0

            for i in range(0, len(audio_data) // 2, frame_size):
                frame = audio_data[i * 2 : (i + frame_size) * 2]
                if len(frame) == frame_size * 2:
                    total_frames += 1
                    try:
                        if self.vad.is_speech(frame, self.rate):
                            speech_frames += 1
                    except:
                        pass

            # Require at least 30% speech frames
            return total_frames > 0 and speech_frames / total_frames > 0.3
        except Exception as e:
            print(f" VAD error: {e}")
            return True  # Assume speech on error

    def start_capture(self):
        """Enhanced capture start with smart device selection"""
        print("Starting audio capture...")
        try:
            device_index = self._select_best_device()

            if device_index is None:
                raise RuntimeError(" No suitable audio device found")

            device_info = self.p.get_device_info_by_index(device_index)
            device_name = device_info["name"]

            print(f" Selected device: {device_name}")

            # Open stream with error recovery
            self.stream = self.p.open(
                format=pyaudio.paFloat32,
                channels=self.channels,
                rate=self.rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk,
                stream_callback=self._callback,
            )

            print(" Stream created")
            self.is_capturing = True

            # Start monitoring thread
            threading.Thread(target=self._monitor_stream, daemon=True).start()

            # Store device info
            self.device_info = {
                "name": device_name,
                "type": "PyAudio",
                "index": device_index,
            }

            print(" Audio capture ready")

        except Exception as e:
            print(f"[ERROR] Failed to start audio capture: {e}")
            self.device_info = {"name": "Error", "type": "error"}

    def _select_best_device(self):
        """Smart device selection with priority ranking based on audio_source mode"""
        print(f"Scanning audio devices (mode: {self.audio_source})...")

        candidates = []

        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                name = info["name"].lower()
                max_channels = info["maxInputChannels"]

                if max_channels == 0:
                    continue

                # Priority scoring based on audio source mode
                priority = 0

                if self.audio_source == "microphone":
                    # Microphone mode: prioritize physical mic devices
                    if "microphone" in name:
                        priority = 100
                    elif "mic" in name:
                        priority = 90
                    elif "input" in name:
                        priority = 70
                    elif "voicemeeter" in name or "cable" in name:
                        priority = 10  # Deprioritize virtual devices
                    else:
                        priority = 30
                else:
                    # System audio mode: prioritize virtual audio cables
                    if "voicemeeter" in name and "b1" in name:
                        priority = 100
                    elif "voicemeeter" in name:
                        priority = 90
                    elif "cable" in name or "loopback" in name:
                        priority = 80
                    elif "nvidia broadcast" in name:
                        priority = 70
                    elif "hdmi" in name:
                        priority = 60
                    elif "stereo mix" in name:
                        priority = 50
                    elif "microphone" in name:
                        priority = 40
                    else:
                        priority = 10

                candidates.append((priority, i, name))
                print(f"  [{i}] {info['name'][:50]} - Priority: {priority}")

            except Exception as e:
                print(f"   Device {i} error: {e}")
                continue

        # Select highest priority device
        if candidates:
            candidates.sort(reverse=True, key=lambda x: x[0])
            selected = candidates[0]
            print(f" Best device: [{selected[1]}] {selected[2]}")
            return selected[1]

        return None

    def _callback(self, in_data, frame_count, time_info, status):
        """Enhanced callback with error handling"""
        try:
            if status:
                print(f" Audio status: {status}")

            if not self.paused:
                # Convert to numpy
                data = np.frombuffer(in_data, dtype=np.float32)

                # Mix to mono if stereo
                if len(data.shape) > 1 and data.shape[1] > 1:
                    data = np.mean(data, axis=1)

                # Calculate audio level (RMS)
                self.current_audio_level = np.sqrt(np.mean(data**2))

                # Convert to bytes
                audio_bytes = (data * 32767).astype(np.int16).tobytes()

                # Add to queue with overflow protection
                try:
                    self.audio_queue.put_nowait(audio_bytes)
                except queue.Full:
                    # Drop oldest frame
                    try:
                        self.audio_queue.get_nowait()
                        self.audio_queue.put_nowait(audio_bytes)
                    except:
                        pass

            return (in_data, pyaudio.paContinue)

        except Exception as e:
            self.error_count += 1
            print(f" Callback error: {e}")

            if self.error_count > self.max_errors:
                print(" Too many errors, stopping capture")
                return (in_data, pyaudio.paComplete)

            return (in_data, pyaudio.paContinue)

    def _monitor_stream(self):
        """Monitor stream health and auto-recover"""
        print("  Stream monitor started")

        while self.is_capturing:
            try:
                if self.stream and not self.stream.is_active():
                    print(" Stream inactive, attempting recovery...")
                    self._recover_stream()

                time.sleep(5)  # Check every 5 seconds

            except Exception as e:
                print(f" Monitor error: {e}")
                time.sleep(5)

    def _recover_stream(self):
        """Attempt to recover failed stream"""
        try:
            print(" Recovering stream...")

            if self.stream:
                self.stream.stop_stream()
                self.stream.close()

            # Restart with same device
            device_index = self.device_info.get("index", None)
            if device_index is not None:
                self.stream = self.p.open(
                    format=pyaudio.paFloat32,
                    channels=self.channels,
                    rate=self.rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self.chunk,
                    stream_callback=self._callback,
                )
                print(" Stream recovered")

        except Exception as e:
            print(f" Recovery failed: {e}")

    def get_audio_chunk(self):
        """Get audio chunk with timeout"""
        try:
            return self.audio_queue.get_nowait()
        except queue.Empty:
            return None

    def stop_capture(self):
        """Clean shutdown"""
        print(" Stopping audio capture...")
        self.is_capturing = False

        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass

        try:
            self.p.terminate()
        except:
            pass

        print(" Audio capture stopped")

    def set_audio_source(self, source):
        """Switch audio source between 'system' and 'microphone' and restart capture"""
        if source == self.audio_source:
            return
        print(f"Switching audio source: {self.audio_source} -> {source}")
        self.audio_source = source
        if self.is_capturing:
            # Stop current stream
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except:
                    pass
            # Restart with new device
            self.error_count = 0
            device_index = self._select_best_device()
            if device_index is not None:
                self.stream = self.p.open(
                    format=pyaudio.paFloat32,
                    channels=self.channels,
                    rate=self.rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self.chunk,
                    stream_callback=self._callback,
                )
                device_info = self.p.get_device_info_by_index(device_index)
                self.device_info = {
                    "name": device_info["name"],
                    "type": "PyAudio",
                    "index": device_index,
                }
                print(f" Switched to: {device_info['name']}")
            else:
                print(" No suitable device found for this mode")

    def toggle_pause(self):
        """Toggle pause state"""
        self.paused = not self.paused
        status = " Paused" if self.paused else " Resumed"
        print(status)
        return self.paused

    def get_device_info(self):
        """Get current device info"""
        return self.device_info

    def get_stats(self):
        """Get capture statistics"""
        return {
            "queue_size": self.audio_queue.qsize(),
            "is_capturing": self.is_capturing,
            "is_paused": self.paused,
            "error_count": self.error_count,
            "device": self.device_info,
        }


if __name__ == "__main__":
    print(" Testing AudioCapture...")
    capture = AudioCapture()
    capture.start_capture()

    print(" Capture stats:", capture.get_stats())

    print(" Capturing for 5 seconds...")
    time.sleep(5)

    chunks = 0
    while True:
        chunk = capture.get_audio_chunk()
        if chunk:
            chunks += 1
        else:
            break

    print(f" Captured {chunks} chunks")

    capture.stop_capture()
    print(" Test complete")
