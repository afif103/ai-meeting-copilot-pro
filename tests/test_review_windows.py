"""Minimal LOCAL Tkinter smoke test for the review-window wiring.

The privacy/isolation LOGIC is covered headlessly and in CI by
test_window_registry.py (window closing + owner guard) and
test_memory_review.py (per-session edit isolation). This file only
confirms the GUI is wired to that logic; it needs a display, so it
auto-skips in a headless environment. One app instance / one Tk root to
avoid multi-root fragility.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from _util import fake_summary, temp_env  # noqa: E402

# Import the app behind a guard - skip the whole module if Tkinter has no
# display or the heavy audio/ML deps are missing (e.g. headless CI).
try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    import desktop_app
    from backend import memory_review, profile_store, session_store
    _HAVE_UI = True
    _SKIP = ""
except Exception as e:  # pragma: no cover - environment dependent
    _HAVE_UI = False
    _SKIP = f"UI unavailable: {e}"

pytestmark = pytest.mark.skipif(not _HAVE_UI, reason=_SKIP)


def _live_toplevels(app):
    """All live Toplevels anywhere under root (transcript popups are
    children of the session-review window, not of root)."""
    found = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Toplevel) and c.winfo_exists():
                found.append(c)
            walk(c)

    walk(app.root)
    return found


def _find_button(widget, text, acc):
    for c in widget.winfo_children():
        if isinstance(c, tk.Button) and c.cget("text") == text:
            acc.append(c)
        _find_button(c, text, acc)
    return acc


def test_review_window_smoke():
    """One app instance (avoids Tk multi-root flakiness) covering: window
    registration, transcript-popup registration, profile-switch closing of
    ALL of a profile's windows, and a rendering failure leaving no
    untracked window. The isolation LOGIC itself is covered headlessly in
    test_window_registry.py / test_memory_review.py."""
    with temp_env():
        profile_store.ensure_default_profile()
        a = profile_store.create_profile("A")
        b = profile_store.create_profile("B")
        profile_store.set_active_profile_id(a["id"])
        app = desktop_app.AICoplotPro("default")
        app.root.update()
        from tkinter import messagebox
        messagebox.showerror = lambda *x, **k: None
        messagebox.showwarning = lambda *x, **k: None

        def _new_session():
            m = session_store.create_session("transcript body.",
                                             mode_id="meeting_discussion")
            session_store.save_summary(
                m["session_id"],
                fake_summary([{"category": "decision", "text": "Ship Friday",
                               "reason": "r", "confidence": "high"}]),
                a["id"])
            return m["session_id"]

        try:
            # --- registration + transcript popup + Approved Memory +
            #     profile-switch cleanup ---
            sid = _new_session()
            sr = app._open_session_review(sid, a["id"])
            rv = app._open_memory_review(sid, a["id"])
            # read-only check: Approved Memory open + refresh must not touch
            # any of profile A's memory files
            a_mem = profile_store.get_profile_memory_dir(a["id"])
            mem_before = {f.name: f.read_bytes() for f in a_mem.glob("*.md")}
            am = app._open_approved_memory()  # Packet 7C read-only window
            app.root.update()
            am._render()  # exercise Refresh
            app.root.update()
            mem_after = {f.name: f.read_bytes() for f in a_mem.glob("*.md")}
            assert mem_after == mem_before  # read-only: no source file changed
            assert sr.winfo_exists() and rv.winfo_exists() and am.winfo_exists()
            assert hasattr(rv, "_text_widgets")
            assert hasattr(am, "_render")  # Approved Memory has a Refresh hook

            btns = _find_button(sr, "Open Transcript", [])
            assert btns
            btns[0].invoke()  # opens + registers the transcript popup
            app.root.update()
            # session + memory + approved-memory + transcript
            assert len(_live_toplevels(app)) >= 4

            app._refresh_profiles()
            app.profile_combo.current(app._profile_ids.index(b["id"]))
            app._on_profile_selected()
            app.root.update()
            assert _live_toplevels(app) == []  # all of A's windows closed
            assert not am.winfo_exists()  # Approved Memory closed on switch

            # --- rendering failure leaves no untracked window ---
            profile_store.set_active_profile_id(a["id"])
            sid2 = _new_session()
            before = len(_live_toplevels(app))
            app._build_memory_review = lambda *x, **k: (_ for _ in ()).throw(
                RuntimeError("render boom"))
            result = app._open_memory_review(sid2, a["id"])
            app.root.update()
            assert result is None
            assert len(_live_toplevels(app)) == before  # partial window gone
            assert a["id"] not in app._review_windows.owners()
        finally:
            app.root.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
