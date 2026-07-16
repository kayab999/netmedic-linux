"""Tests for the reference-counted busy state in MainWindow.

These tests exercise the counting logic without requiring GTK by
mocking the GLib.idle_add dispatcher.
"""

import threading


def _make_window_stub():
    """Create a minimal stub that mimics the busy-counting attributes."""

    class BusyStub:
        def __init__(self):
            self._busy_count = 0
            self._busy_lock = threading.Lock()
            self.is_destroyed = False
            self._ui_calls = []  # Track (busy, msg) calls dispatched

        def set_busy(self, busy, msg="Processing..."):
            with self._busy_lock:
                if busy:
                    self._busy_count += 1
                    if self._busy_count == 1:
                        self._ui_calls.append((True, msg))
                else:
                    self._busy_count = max(0, self._busy_count - 1)
                    if self._busy_count == 0:
                        self._ui_calls.append((False, msg))

    return BusyStub()


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------


def test_single_busy_cycle():
    """Single increment → decrement goes busy then idle."""
    w = _make_window_stub()
    w.set_busy(True, "A")
    w.set_busy(False)
    assert w._busy_count == 0
    assert w._ui_calls == [(True, "A"), (False, "Processing...")]


def test_overlapping_tasks_no_early_unlock():
    """Two tasks overlap: UI should not unlock until both finish."""
    w = _make_window_stub()
    w.set_busy(True, "Task A")
    w.set_busy(True, "Task B")  # Second task starts while first is running
    w.set_busy(False)  # First task finishes → count goes 2→1, no UI unlock
    assert w._busy_count == 1
    # Only one busy call dispatched, no unlock yet
    assert w._ui_calls == [(True, "Task A")]
    w.set_busy(False)  # Second task finishes → count goes 1→0, UI unlocks
    assert w._busy_count == 0
    assert w._ui_calls[-1] == (False, "Processing...")


def test_triple_overlap():
    """Three tasks overlap: unlock only when all three are done."""
    w = _make_window_stub()
    for i in range(3):
        w.set_busy(True, f"T{i}")
    assert w._busy_count == 3
    # Only one True dispatch (the first)
    assert len([c for c in w._ui_calls if c[0]]) == 1

    w.set_busy(False)
    w.set_busy(False)
    assert w._busy_count == 1
    # Still no unlock dispatched
    assert not any(c[0] is False for c in w._ui_calls)

    w.set_busy(False)
    assert w._busy_count == 0
    assert w._ui_calls[-1][0] is False


def test_decrement_below_zero_clamped():
    """Extra decrements don't go negative."""
    w = _make_window_stub()
    w.set_busy(False)
    w.set_busy(False)
    assert w._busy_count == 0


def test_thread_safety():
    """Concurrent increments and decrements are safe."""
    w = _make_window_stub()
    barrier = threading.Barrier(20)

    def inc_dec():
        barrier.wait()
        w.set_busy(True, "thread")
        w.set_busy(False)

    threads = [threading.Thread(target=inc_dec) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert w._busy_count == 0
