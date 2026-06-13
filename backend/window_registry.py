"""
GUI-agnostic registry for profile-bound review windows.

The privacy-critical behavior - "a window that belongs to profile A is
closed the moment another profile becomes active" - lives here, not in the
Tkinter code, so it can be tested headlessly (in CI) with fake window
objects. A "window" only needs two methods: winfo_exists() -> bool and
destroy(). Tkinter Toplevels satisfy this; so do tiny test doubles.

Stdlib only (in fact, no imports needed).
"""


def owner_is_active(active_profile_id, owner_profile_id):
    """Decision used by the review UI: an action on a session's owning
    profile is allowed ONLY when that profile is currently active.
    A missing owner, or no active profile, is never 'active'."""
    return owner_profile_id is not None and active_profile_id == owner_profile_id


class WindowRegistry:
    """Tracks review windows by the profile they belong to.

    close_foreign(active) destroys every tracked window whose owner is not
    the active profile, so one profile's session content is never left on
    screen under another profile. Dead windows are pruned automatically.
    """

    # Three-state existence: a raised winfo_exists() is UNKNOWN, never
    # proof that the window is gone.
    ALIVE = "alive"
    GONE = "gone"
    UNKNOWN = "unknown"

    def __init__(self):
        self._items = []  # list of (window, owner_profile_id)

    @classmethod
    def _existence(cls, window):
        try:
            return cls.ALIVE if window.winfo_exists() else cls.GONE
        except Exception:
            return cls.UNKNOWN  # cannot confirm either way

    def _neutralize(self, window):
        """Try to make a window not-visible. Returns "gone", "hidden", or
        "failed". destroy() is attempted; only a CONFIRMED-gone existence
        check counts as gone (a raised check does not). If not gone, try
        withdraw(); if neither can be confirmed safe, "failed"."""
        try:
            window.destroy()
        except Exception:
            pass
        if self._existence(window) == self.GONE:
            return "gone"
        withdraw = getattr(window, "withdraw", None)
        if callable(withdraw):
            try:
                withdraw()
                return "hidden"
            except Exception:
                return "failed"
        return "failed"

    def register(self, window, owner_profile_id):
        """Track a window under its owning profile. Prunes ONLY
        definitely-gone entries; unknown-state windows are retained."""
        self._items = [(w, o) for (w, o) in self._items
                       if self._existence(w) != self.GONE]
        self._items.append((window, owner_profile_id))

    def close_foreign(self, active_profile_id):
        """Close (or hide) every tracked window NOT owned by the active
        profile - including ownerless windows and (with active None) every
        window. A window is kept visible only when owner_is_active() is
        True. Returns the list of windows that could not be confirmed
        safe (still possibly visible) after trying destroy() then
        withdraw(); such windows STAY tracked (never silently discarded)
        so the caller can report the privacy failure. Definitely-gone
        windows are pruned; unknown-state windows are never dropped
        without a neutralize attempt.
        """
        survivors = []
        failures = []
        for window, owner in self._items:
            if self._existence(window) == self.GONE:
                continue  # definitely gone -> prune
            # alive OR unknown
            if owner_is_active(active_profile_id, owner):
                survivors.append((window, owner))  # active profile: keep
                continue
            status = self._neutralize(window)
            if status == "gone":
                continue  # confirmed gone -> drop
            if status == "hidden":
                survivors.append((window, owner))  # safe but still exists
                continue
            # status == "failed": not confirmed safe - keep tracked AND report
            failures.append(window)
            survivors.append((window, owner))
        self._items = survivors
        return failures

    def owners(self):
        """Owning profile ids of tracked windows. Prunes ONLY
        definitely-gone windows; unknown-state windows are retained."""
        self._items = [(w, o) for (w, o) in self._items
                       if self._existence(w) != self.GONE]
        return [o for _, o in self._items]
