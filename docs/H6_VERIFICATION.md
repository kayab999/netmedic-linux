# H6 verification — AI pilot disruptive actions require confirmation

Verified 2026-11-17 against `netmedic/netmedic/ai_console.py`.

- Disruptive actions are identified via `is_disruptive(action)` imported from
  `action_catalog` (line 4, used at line 267).
- The only execution path is `_confirm_and_execute(action, params)` (line 256).
  It is wired to the preview's execute button at line 222:
  `execute_btn.connect("clicked", lambda b: self._confirm_and_execute(action, params))`.
- For disruptive actions (line 267), the dialog title and message include the
  validated params via `_format_args(params)` (lines 149-158, 274), so the user
  sees the exact arguments before `confirmed=True` is sent (line 302).
- The non-disruptive `user_intent` call (line 130) is a safe read-only intent
  parse and never executes a privileged action directly.
- Conclusion: no disruptive action reaches `client.ask(..., confirmed=True)`
  without the parameter-showing confirmation dialog. H6 satisfied.
