"""Tests for the headless Trainer voice controller (Packet 8B).

No real microphone, Whisper model, profile, or network is used - the
recorder, transcriber, scheduler, spawner, and timer are all injected
fakes, so the full record -> temp-WAV -> transcribe lifecycle runs
deterministically and in-process.
"""

import glob
import os
import queue
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from backend import trainer_voice as tv  # noqa: E402


class FakeRecorder:
    def __init__(self, *, fail=False, stop_fail=False,
                 audio=b"\x01\x00" * 1600, name="Fake Mic"):
        self.fail = fail
        self.stop_fail = stop_fail
        self.audio = audio
        self.device_name = name
        self.started = False
        self.stopped = False

    def start(self):
        if self.fail:
            raise RuntimeError("no microphone")
        self.started = True

    def stop(self):
        self.stopped = True
        if self.stop_fail:
            raise RuntimeError("microphone device error")
        return self.audio


class FakeTimer:
    def __init__(self, delay, fn):
        self.delay = delay
        self.fn = fn
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.fn()


def _make(tmp_path, *, transcribe=None, recorder_fail=False,
          recorder_stop_fail=False, recorder_audio=b"\x01\x00" * 1600,
          spawn_mode="sync", schedule_mode="sync"):
    ctx = {"events": [], "recorders": [], "timers": [],
           "spawned": [], "scheduled": [], "transcribe_calls": [],
           "wav_existed": []}

    def transcribe_fn(path):
        ctx["transcribe_calls"].append(path)
        ctx["wav_existed"].append(os.path.exists(path))
        if transcribe is None:
            return "hello answer"
        return transcribe(path)

    def recorder_factory():
        r = FakeRecorder(fail=recorder_fail, stop_fail=recorder_stop_fail,
                         audio=recorder_audio)
        ctx["recorders"].append(r)
        return r

    def spawn(fn):
        if spawn_mode == "sync":
            fn()
        else:
            ctx["spawned"].append(fn)

    def schedule(fn):
        if schedule_mode == "sync":
            fn()
        else:
            ctx["scheduled"].append(fn)

    def timer_factory(delay, fn):
        t = FakeTimer(delay, fn)
        ctx["timers"].append(t)
        return t

    def on_state(state, info):
        ctx["events"].append((state, dict(info)))

    c = tv.TrainerVoiceController(
        recorder_factory, transcribe_fn, schedule, on_state,
        max_seconds=120, temp_dir=str(tmp_path), spawn=spawn,
        timer_factory=timer_factory)
    return c, ctx


def _no_wavs(tmp_path):
    return glob.glob(os.path.join(str(tmp_path), "trainer_ans_*.wav")) == []


def test_initial_ready_state(tmp_path):
    c, ctx = _make(tmp_path)
    assert c.state == tv.READY
    assert c.transcript == ""
    assert c.is_busy is False
    assert ctx["events"] == []


def test_start_begins_exactly_one_recording(tmp_path):
    c, ctx = _make(tmp_path, schedule_mode="defer", spawn_mode="defer")
    assert c.start("cc_easy_1") is True
    assert c.state == tv.RECORDING
    assert c.is_busy is True
    assert len(ctx["recorders"]) == 1 and ctx["recorders"][0].started
    assert ctx["events"][-1][0] == tv.RECORDING
    assert ctx["events"][-1][1]["device_name"] == "Fake Mic"


def test_repeated_start_cannot_create_second_recording(tmp_path):
    c, ctx = _make(tmp_path, schedule_mode="defer", spawn_mode="defer")
    assert c.start("cc_easy_1") is True
    assert c.start("cc_easy_2") is False  # already recording
    assert len(ctx["recorders"]) == 1
    assert c.state == tv.RECORDING


def test_stop_transcribes_once_and_shows_text(tmp_path):
    c, ctx = _make(tmp_path)
    c.start("cc_easy_1")
    assert c.stop() is True
    assert ctx["recorders"][0].stopped is True
    assert len(ctx["transcribe_calls"]) == 1     # transcription ran once
    assert c.state == tv.READY
    assert c.transcript == "hello answer"
    ok = [e for e in ctx["events"] if e[0] == tv.READY
          and e[1].get("status") == "ok"]
    assert ok and ok[-1][1]["transcript"] == "hello answer"
    assert _no_wavs(tmp_path)                     # temp WAV cleaned up


def test_busy_during_recording_and_transcribing(tmp_path):
    c, ctx = _make(tmp_path, spawn_mode="defer", schedule_mode="defer")
    c.start("cc_easy_1")
    assert c.is_busy is True and c.state == tv.RECORDING
    c.stop()
    assert c.is_busy is True and c.state == tv.TRANSCRIBING
    ctx["spawned"].pop()()      # run the transcription worker
    ctx["scheduled"].pop()()    # deliver the result
    assert c.is_busy is False and c.state == tv.READY


def test_empty_transcription_reports_no_speech(tmp_path):
    c, ctx = _make(tmp_path, transcribe=lambda p: "")
    c.start("cc_easy_1")
    c.stop()
    assert c.transcript == ""
    empty = [e for e in ctx["events"] if e[1].get("status") == "empty"]
    assert empty
    assert _no_wavs(tmp_path)


def test_transcription_error_restores_ready(tmp_path):
    def boom(path):
        raise RuntimeError("whisper failed")
    c, ctx = _make(tmp_path, transcribe=boom)
    c.start("cc_easy_1")
    c.stop()
    assert c.state == tv.READY
    err = [e for e in ctx["events"] if e[1].get("status") == "error"]
    assert err
    assert _no_wavs(tmp_path)                     # cleaned up even on error


def test_temp_wav_exists_during_transcribe_then_deleted(tmp_path):
    c, ctx = _make(tmp_path)
    c.start("cc_easy_1")
    c.stop()
    assert ctx["wav_existed"] == [True]           # existed during transcribe
    assert not os.path.exists(ctx["transcribe_calls"][0])  # deleted after
    assert _no_wavs(tmp_path)


def test_clear_removes_transcript(tmp_path):
    c, ctx = _make(tmp_path)
    c.start("cc_easy_1")
    c.stop()
    assert c.transcript == "hello answer"
    assert c.clear() is True
    assert c.transcript == "" and c.question_id is None
    assert ctx["events"][-1][1]["status"] == "cleared"


def test_clear_blocked_while_busy(tmp_path):
    c, ctx = _make(tmp_path, spawn_mode="defer", schedule_mode="defer")
    c.start("cc_easy_1")
    assert c.clear() is False                     # cannot clear mid-recording
    c.stop()
    assert c.clear() is False                     # cannot clear mid-transcribe


def test_question_id_tracks_recording(tmp_path):
    c, _ = _make(tmp_path)
    c.start("va_hard_3")
    assert c.question_id == "va_hard_3"
    c.stop()
    assert c.question_id == "va_hard_3"           # owns the recorded question


def test_recording_limit_takes_safe_stop_path(tmp_path):
    c, ctx = _make(tmp_path)
    c.start("cc_easy_1")
    assert ctx["timers"][-1].delay == 120         # 120-second cap armed
    ctx["timers"][-1].fire()                       # limit reached
    assert ctx["recorders"][0].stopped is True
    assert c.state == tv.READY
    ok = [e for e in ctx["events"] if e[1].get("status") == "ok"]
    assert ok and ok[-1][1]["limit_reached"] is True
    assert _no_wavs(tmp_path)


def test_missing_microphone_fails_closed(tmp_path):
    c, ctx = _make(tmp_path, recorder_fail=True)
    assert c.start("cc_easy_1") is False
    assert c.state == tv.READY                    # stays usable
    assert ctx["recorders"][0].started is False
    assert not ctx["recorders"][0].stopped
    assert ctx["events"][-1][1]["status"] == "mic_unavailable"
    assert ctx["transcribe_calls"] == []          # no worker started
    assert _no_wavs(tmp_path)


def test_recorder_stop_failure_is_error_not_no_speech(tmp_path):
    # A microphone/device failure in recorder.stop() is a recording ERROR,
    # not the no-speech path.
    c, ctx = _make(tmp_path, recorder_stop_fail=True)
    assert c.start("q1") is True                   # Start succeeds
    c.stop()                                        # Stop returns safely
    assert c.state == tv.READY                      # back to READY
    statuses = [e[1].get("status") for e in ctx["events"]]
    assert "error" in statuses and "empty" not in statuses
    assert ctx["transcribe_calls"] == []            # transcriber never called
    assert _no_wavs(tmp_path)                         # no temporary WAV
    # a later recording attempt can start normally
    assert c.start("q2") is True
    assert c.state == tv.RECORDING


def test_recording_limit_with_stop_failure_is_error(tmp_path):
    c, ctx = _make(tmp_path, recorder_stop_fail=True)
    c.start("q1")
    ctx["timers"][-1].fire()                        # cap -> stop(limit) raises
    assert c.state == tv.READY                       # did not crash
    statuses = [e[1].get("status") for e in ctx["events"]]
    assert "error" in statuses and "empty" not in statuses
    assert ctx["transcribe_calls"] == []
    assert _no_wavs(tmp_path)


def test_cancel_before_worker_starts_bails_completely(tmp_path):
    c, ctx = _make(tmp_path, spawn_mode="defer", schedule_mode="defer")
    c.start("cc_easy_1")
    c.stop()                                       # worker deferred (not run)
    c.cancel()                                     # cancel BEFORE it begins
    assert c.state == tv.READY and c.transcript == ""
    ctx["spawned"].pop()()                         # run the now-stale worker
    assert ctx["transcribe_calls"] == []           # transcriber NOT called
    assert ctx["scheduled"] == []                  # no completion queued
    assert _no_wavs(tmp_path)                       # no temp WAV created
    ok = [e for e in ctx["events"] if e[1].get("status") == "ok"]
    assert ok == []


def test_cancel_during_recording_stops_and_cleans(tmp_path):
    c, ctx = _make(tmp_path, spawn_mode="defer", schedule_mode="defer")
    c.start("cc_easy_1")
    c.cancel()
    assert ctx["recorders"][0].stopped is True
    assert c.state == tv.READY and c.transcript == ""
    assert _no_wavs(tmp_path)


def test_close_is_terminal_and_blocks_start(tmp_path):
    c, ctx = _make(tmp_path)
    c.start("cc_easy_1")
    c.close()
    assert c.state == tv.CLOSED
    assert c.start("cc_easy_2") is False           # closed -> no new recording
    assert ctx["recorders"][0].stopped is True     # active recording stopped
    assert _no_wavs(tmp_path)


def test_close_before_worker_starts_bails(tmp_path):
    c, ctx = _make(tmp_path, spawn_mode="defer", schedule_mode="defer")
    c.start("cc_easy_1")
    c.stop()
    c.close()                                      # close BEFORE worker begins
    ctx["spawned"].pop()()                         # run the now-stale worker
    assert c.state == tv.CLOSED
    assert ctx["transcribe_calls"] == []           # transcriber NOT called
    assert ctx["scheduled"] == []                  # no completion queued
    assert _no_wavs(tmp_path)                       # no temp WAV created


def test_empty_capture_is_no_speech_without_wav_or_transcriber(tmp_path):
    c, ctx = _make(tmp_path, recorder_audio=b"")   # recorder returns nothing
    c.start("cc_easy_1")
    c.stop()
    assert ctx["transcribe_calls"] == []           # transcriber NOT called
    assert _no_wavs(tmp_path)                        # no temp WAV created
    assert c.state == tv.READY
    statuses = [e[1].get("status") for e in ctx["events"]]
    assert "empty" in statuses and "error" not in statuses
    assert c.transcript == ""


def test_empty_capture_preserves_limit_reached(tmp_path):
    c, ctx = _make(tmp_path, recorder_audio=b"")
    c.start("cc_easy_1")
    ctx["timers"][-1].fire()                        # 120s cap -> safe stop
    empty = [e for e in ctx["events"] if e[1].get("status") == "empty"]
    assert empty and empty[-1][1]["limit_reached"] is True
    assert ctx["transcribe_calls"] == []
    assert _no_wavs(tmp_path)


def test_ui_callback_marshalled_off_worker_thread(tmp_path):
    # Correction 1: the worker thread transcribes and only QUEUES the result;
    # the UI mutation (_finish) runs on the draining (main) thread.
    main_id = threading.get_ident()
    ids = {}
    cbq = queue.Queue()
    threads = []
    events = []

    def transcribe(path):
        ids["transcribe"] = threading.get_ident()
        return "answer"

    def schedule(fn):
        ids["schedule"] = threading.get_ident()    # thread-safe put only
        cbq.put(fn)

    def spawn(fn):
        t = threading.Thread(target=fn)
        t.start()
        threads.append(t)

    def on_state(state, info):
        events.append((state, threading.get_ident(), dict(info)))

    rec = FakeRecorder()
    c = tv.TrainerVoiceController(lambda: rec, transcribe, schedule, on_state,
                                 temp_dir=str(tmp_path), spawn=spawn)
    c.start("q1")
    c.stop()
    threads[0].join(3)                             # worker finished
    assert ids["transcribe"] != main_id            # transcribed off-thread
    assert ids["schedule"] != main_id              # queued off-thread
    assert c.transcript == ""                       # NOT applied until drained
    cbq.get_nowait()()                              # drain on the main thread
    assert c.transcript == "answer"
    ok = [e for e in events if e[2].get("status") == "ok"]
    assert ok and ok[-1][1] == main_id             # UI mutation on main thread


def test_cancel_while_transcribing_discards_result(tmp_path):
    # Correction 2: cancellation during a non-interruptible local transcribe
    # lets the call return but discards the result (no callback delivered).
    started = threading.Event()
    release = threading.Event()
    cbq = queue.Queue()
    threads = []
    events = []

    def transcribe(path):
        started.set()
        release.wait(3)                            # block until released
        return "late answer"

    def spawn(fn):
        t = threading.Thread(target=fn)
        t.start()
        threads.append(t)

    rec = FakeRecorder()
    c = tv.TrainerVoiceController(
        lambda: rec, transcribe, lambda fn: cbq.put(fn),
        lambda s, i: events.append((s, dict(i))),
        temp_dir=str(tmp_path), spawn=spawn)
    c.start("q1")
    c.stop()
    assert started.wait(3)                         # transcribe is running
    c.cancel()                                      # cancel WHILE it runs
    release.set()                                   # let the local call return
    threads[0].join(3)
    assert cbq.empty()                              # no completion delivered
    assert [e for e in events if e[1].get("status") == "ok"] == []
    assert _no_wavs(tmp_path)                        # temp WAV deleted
    assert c.transcript == ""


# ---------- Correction 1: temp-WAV write-failure cleanup ----------

def test_wave_open_failure_leaves_no_temp_and_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(tv.wave, "open",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    c, ctx = _make(tmp_path)                       # non-empty audio
    c.start("q1")
    c.stop()
    assert ctx["transcribe_calls"] == []           # transcriber NOT called
    assert _no_wavs(tmp_path)                        # mkstemp file deleted
    assert c.state == tv.READY
    assert [e for e in ctx["events"] if e[1].get("status") == "error"]


def test_writeframes_failure_leaves_no_temp(tmp_path, monkeypatch):
    class _BadWriter:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def setnchannels(self, n):
            pass

        def setsampwidth(self, n):
            pass

        def setframerate(self, n):
            pass

        def writeframes(self, data):
            raise OSError("write error")

    monkeypatch.setattr(tv.wave, "open", lambda *a, **k: _BadWriter())
    c, ctx = _make(tmp_path)
    c.start("q1")
    c.stop()
    assert _no_wavs(tmp_path)                        # no leaked temp WAV
    assert ctx["transcribe_calls"] == []
    assert c.state == tv.READY
    assert [e for e in ctx["events"] if e[1].get("status") == "error"]


# ---------- Correction 3: production transcribe adapter ----------

class _FakeProdTranscriber:
    """Mimics TranscriptionService: has_speech() + _transcribe_audio()."""

    def __init__(self, *, speech=True, text="hello"):
        self._speech = speech
        self._text = text
        self.transcribe_called = False

    def has_speech(self, audio):
        return self._speech

    def _transcribe_audio(self, audio):
        self.transcribe_called = True
        return self._text


def _tiny_wav(tmp_path, name="probe.wav"):
    import wave
    p = str(tmp_path / name)
    with wave.open(p, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x01\x00" * 1600)
    return p


def test_make_transcribe_no_speech_returns_empty(tmp_path):
    t = _FakeProdTranscriber(speech=False)
    out = tv.make_transcribe_fn(lambda: t)(_tiny_wav(tmp_path))
    assert out == ""                                # -> 'No speech detected'
    assert t.transcribe_called is False             # didn't bother transcribing


def test_make_transcribe_speech_but_none_raises(tmp_path):
    t = _FakeProdTranscriber(speech=True, text=None)
    with pytest.raises(Exception):                  # speech present, no text
        tv.make_transcribe_fn(lambda: t)(_tiny_wav(tmp_path))


def test_make_transcribe_speech_with_text_succeeds(tmp_path):
    t = _FakeProdTranscriber(speech=True, text="my answer")
    assert tv.make_transcribe_fn(lambda: t)(_tiny_wav(tmp_path)) == "my answer"


def test_make_transcribe_none_transcriber_raises(tmp_path):
    with pytest.raises(Exception):
        tv.make_transcribe_fn(lambda: None)(_tiny_wav(tmp_path))


def test_make_transcribe_without_has_speech_fallback(tmp_path):
    class _NoVad:
        def _transcribe_audio(self, audio):
            return "txt"

    assert tv.make_transcribe_fn(lambda: _NoVad())(_tiny_wav(tmp_path)) == "txt"


def test_virtual_inputs_are_rejected_for_answer_recording():
    # Voicemeeter / virtual-cable / loopback must never be used to record a
    # spoken answer (they may carry mixed system + interviewer audio).
    for name in ("VoiceMeeter Output (VB-Audio Voi", "VB-Audio Cable Input",
                 "CABLE Output (VB-Audio Virtual)", "Stereo Mix (Realtek)",
                 "Loopback Audio", "VoiceMeeter Aux Input"):
        assert tv._is_virtual_input(name) is True, name


def test_physical_microphones_are_accepted():
    for name in ("Microphone (Realtek High Defini", "Headset Microphone",
                 "USB Audio Device", "Mic in (Conexant)", "Blue Yeti"):
        assert tv._is_virtual_input(name) is False, name


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
