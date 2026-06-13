"""Headless tests for the profile/window isolation logic.

These run in CI (no Tkinter, no display) using fake window doubles, and
cover the privacy-critical behavior: a profile switch closes every review
window owned by another profile, and the owner-active guard decision.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

from backend import window_registry  # noqa: E402


class FakeWindow:
    """Duck-typed stand-in for a Tk Toplevel (winfo_exists / destroy /
    withdraw)."""

    def __init__(self, kind="memory-review"):
        self.kind = kind
        self._alive = True
        self.hidden = False

    def winfo_exists(self):
        return self._alive

    def destroy(self):
        self._alive = False

    def withdraw(self):
        self.hidden = True


class UndestroyableWindow(FakeWindow):
    """destroy() fails but withdraw() works - must be HIDDEN, never dropped
    while still alive."""

    def destroy(self):
        raise RuntimeError("cannot destroy")


class UnclosableWindow(FakeWindow):
    """Neither destroy() nor withdraw() works - must be reported as a
    failure and kept tracked, never silently discarded."""

    def destroy(self):
        raise RuntimeError("cannot destroy")

    def withdraw(self):
        raise RuntimeError("cannot withdraw")


class ExistAlwaysRaises(FakeWindow):
    """winfo_exists() always raises -> UNKNOWN state. destroy()/withdraw()
    still work (inherited)."""

    def winfo_exists(self):
        raise RuntimeError("existence check fails")


class RaisesUntilDestroyed(FakeWindow):
    """winfo_exists() raises while alive, returns False once destroyed -
    a raised check must NOT be read as 'gone' before destroy succeeds."""

    def winfo_exists(self):
        if self._alive:
            raise RuntimeError("check fails while alive")
        return False

    def destroy(self):
        self._alive = False


class RaisesAfterDestroy(FakeWindow):
    """winfo_exists() works while alive, raises after destroy() (so we
    cannot confirm 'gone') - the withdraw() fallback makes it safe."""

    def __init__(self):
        super().__init__()
        self._destroyed = False

    def winfo_exists(self):
        if self._destroyed:
            raise RuntimeError("post-destroy check fails")
        return self._alive

    def destroy(self):
        self._destroyed = True


class AllChecksFail(FakeWindow):
    """winfo_exists(), destroy(), and withdraw() all raise."""

    def winfo_exists(self):
        raise RuntimeError("existence check fails")

    def destroy(self):
        raise RuntimeError("destroy fails")

    def withdraw(self):
        raise RuntimeError("withdraw fails")


def test_owner_is_active_decision():
    assert window_registry.owner_is_active("a", "a") is True
    assert window_registry.owner_is_active("b", "a") is False
    assert window_registry.owner_is_active(None, "a") is False
    assert window_registry.owner_is_active("a", None) is False


def test_profile_switch_closes_foreign_memory_and_session_windows():
    reg = window_registry.WindowRegistry()
    mem_a = FakeWindow("memory-review")     # owned by A
    sess_a = FakeWindow("session-review")   # owned by A
    mem_b = FakeWindow("memory-review")     # owned by B
    reg.register(mem_a, "a")
    reg.register(sess_a, "a")
    reg.register(mem_b, "b")

    # Switch to B: both of A's windows (memory-review AND session-review)
    # must close; B's window stays.
    reg.close_foreign("b")
    assert mem_a.winfo_exists() is False
    assert sess_a.winfo_exists() is False
    assert mem_b.winfo_exists() is True
    assert reg.owners() == ["b"]


def test_switch_to_no_active_profile_closes_everything():
    reg = window_registry.WindowRegistry()
    w = FakeWindow()
    reg.register(w, "a")
    reg.close_foreign(None)  # no active profile
    assert w.winfo_exists() is False
    assert reg.owners() == []


def test_active_profile_windows_are_kept():
    reg = window_registry.WindowRegistry()
    w1, w2 = FakeWindow(), FakeWindow()
    reg.register(w1, "a")
    reg.register(w2, "a")
    reg.close_foreign("a")
    assert w1.winfo_exists() and w2.winfo_exists()
    assert reg.owners() == ["a", "a"]


def test_dead_windows_are_pruned():
    reg = window_registry.WindowRegistry()
    dead, live = FakeWindow(), FakeWindow()
    reg.register(dead, "a")
    reg.register(live, "a")
    dead.destroy()  # window closed by the user
    assert reg.owners() == ["a"]  # dead one pruned
    reg.close_foreign("a")
    assert live.winfo_exists()


def test_ownerless_window_is_not_kept_when_no_active_profile():
    # active None + owner None must NOT be treated as active (the old
    # `owner != active` equality bug kept it).
    reg = window_registry.WindowRegistry()
    w = FakeWindow()
    reg.register(w, None)
    failures = reg.close_foreign(None)
    assert w.winfo_exists() is False  # closed, not preserved
    assert failures == []
    assert reg.owners() == []


def test_destroy_failure_falls_back_to_hide():
    reg = window_registry.WindowRegistry()
    w = UndestroyableWindow()
    reg.register(w, "a")
    failures = reg.close_foreign("b")  # foreign
    assert failures == []            # hide counted as success
    assert w.winfo_exists() is True  # still exists (destroy failed)...
    assert w.hidden is True          # ...but hidden -> not visible


def test_unclosable_window_is_reported_and_not_silently_dropped():
    reg = window_registry.WindowRegistry()
    w = UnclosableWindow()
    reg.register(w, "a")
    failures = reg.close_foreign("b")
    assert w in failures                 # reported as a privacy failure
    assert w.winfo_exists() is True       # still alive
    assert "a" in reg.owners()            # still tracked, not discarded


def test_destroy_errors_do_not_raise():
    reg = window_registry.WindowRegistry()
    reg.register(UnclosableWindow(), "a")
    # must not raise even when a window can be neither destroyed nor hidden
    reg.close_foreign("b")


# ---- three-state existence (UNKNOWN must never be read as 'gone') ----

def test_unknown_state_window_is_retained_by_register_and_owners():
    reg = window_registry.WindowRegistry()
    reg.register(ExistAlwaysRaises(), "a")
    # winfo_exists raises -> UNKNOWN -> must NOT be pruned
    assert reg.owners() == ["a"]


def test_exists_raises_before_close_then_destroy_confirms_gone():
    reg = window_registry.WindowRegistry()
    w = RaisesUntilDestroyed()
    reg.register(w, "a")
    failures = reg.close_foreign("b")  # foreign
    assert failures == []
    assert w._alive is False          # destroy() ran and confirmed gone
    assert reg.owners() == []          # pruned only after confirmed gone


def test_exists_raises_after_destroy_uses_withdraw_fallback():
    reg = window_registry.WindowRegistry()
    w = RaisesAfterDestroy()
    reg.register(w, "a")
    failures = reg.close_foreign("b")
    assert failures == []        # could not confirm gone, but hidden = safe
    assert w._destroyed is True  # destroy was attempted
    assert w.hidden is True      # withdraw fallback applied
    assert reg.owners() == ["a"]  # still tracked (existence unknown)


def test_all_checks_fail_is_reported_and_kept_tracked():
    reg = window_registry.WindowRegistry()
    w = AllChecksFail()
    reg.register(w, "a")
    failures = reg.close_foreign("b")
    assert w in failures          # reported as a privacy failure
    assert reg.owners() == ["a"]  # never silently discarded


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
