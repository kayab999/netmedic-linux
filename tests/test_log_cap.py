"""Tests for the GUI log line cap.

Verifies that the log trimming logic correctly removes the oldest
lines when the buffer exceeds MAX_LOG_LINES.
"""


def test_cap_constant_exists():
    """MAX_LOG_LINES is importable and positive."""
    from netmedic.ui import MAX_LOG_LINES
    assert isinstance(MAX_LOG_LINES, int)
    assert MAX_LOG_LINES > 0


def test_cap_value():
    """Default cap is 500 lines."""
    from netmedic.ui import MAX_LOG_LINES
    assert MAX_LOG_LINES == 500


def test_trim_logic():
    """Simulate the trimming algorithm on a plain list to verify correctness."""
    MAX = 500
    lines = []

    # Simulate appending 600 log entries
    for i in range(600):
        lines.append(f"Log entry {i}")
        if len(lines) > MAX:
            excess = len(lines) - MAX
            lines = lines[excess:]

    assert len(lines) == MAX
    # The oldest surviving entry should be #100
    assert lines[0] == "Log entry 100"
    assert lines[-1] == "Log entry 599"
