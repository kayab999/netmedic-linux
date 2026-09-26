# GUI fix notes — theme fill, Infrastructure tab, Renew IP

Working tree on top of `1b66831` (`ui: own headerbar surface`). These three defects showed up together after the Sprint 1 / theme iteration. They are independent. None of them is the fail-closed audit gate.

Reference shots from a known-good session (log line `[06:46:20] ✅ OpenVPN (Angristan): not_installed` on both):

- Basic Repair: dark card, SMART REPAIR blue, **Renew IP Address red**, the other three grid buttons outlined.
- Infrastructure: warning line, three red actions, **VPN Not Installed** / **Install OpenVPN**, client list.

The broken dock shot of Basic Repair kept the dark card and title bar, and painted everything around them white, including the log (`Install health: OK (helper=on)` in black on white). Infrastructure did not become the current page when clicked.

## 1. White page fill and white log

GTK 3 does not paint the notebook page on `notebook`. The page body is an inner `Gtk.Stack`. Basic Repair's `.surface-card` is packed `expand=False`, so it only covers its contents. The leftover region is the stack. Adwaita (light `gtk-theme`, which a dock launch can get even when GNOME chrome is dark) paints that stack white.

The log is a `Gtk.TextView` with style class `log-view`. GTK 3 paints the buffer on the `text` subnode. Rules on `textview.log-view` alone leave that node on the ambient theme: white background, default black text. `viewport` does not cover it.

`theme.py` now owns both:

- `notebook stack, stack` → `#121212` / `#E0E0E0`
- `textview.log-view text` → `#121212` / `#A89984` (selection unchanged)

Checked under `GTK_THEME=Adwaita:light` with Xvfb. A 500×650 stand-in of this layout went from 18015 near-white samples (8391 of them in the log band) to 4 near-white samples and a dark log. `tests/test_theme.py` requires the new selectors and still requires the CSS to parse.

Header bar, frames, and the card were already dark. This did not restyle those.

## 2. Infrastructure tab did not take the click

The page was never removed. `MainWindow` still builds the warning label, the three destructive buttons, and `VPNPanel`. `set_current_page(1)` still shows **VPN Not Installed**. The click never arrived.

`AIConsoleController` mounts a `Gtk.Revealer` (`CROSSFADE`, `valign=START`, full width) on the window `Gtk.Overlay`. A crossfade revealer keeps its child's height while `reveal_child` is false; only opacity changes. On a realized main window that allocation was 510×102 and, in window coordinates, spanned y=87..189. The Infrastructure tab label center was y=112, inside that band. Basic Repair buttons sit lower, so they still clicked. `set_overlay_pass_through(..., True)` was already set and was not enough: the widget stayed mapped and hit-testable over the tab strip. `show_all()` after `mount()` maps it again.

Closed palette now:

- `set_no_show_all(True)` so `show_all()` does not map it
- `hide()` while `reveal_child` and `child-revealed` are both false (`notify::child-revealed` hides again after the close animation)
- pass-through stays on while closed

Opening the palette calls `show()`, then `set_reveal_child(True)`, and turns pass-through off.

After the change, a realized main window reports the revealer `visible=False`, `mapped=False`, allocated height 1. The tab center stays at y=112, outside that sliver. `tests/test_ai_console_overlay.py` requires the closed revealer to be unmapped, height ≤ 1, and pass-through on, and requires show/dismiss to flip visibility.

This is not `record_intent`. That gate runs only after a privileged IPC call. A tab that never becomes current never calls `VPNPanel.refresh_state()`. A stuck busy state would also disable the Basic Repair buttons; those stayed sensitive.

## 3. Renew IP Address lost its red style

Original call, still present at the first commit:

```python
self.btn_ip = self.create_btn("Renew IP Address", self.on_renew_ip, True)
```

`True` is `create_btn(..., destructive=True)`, which adds `destructive-action`. Commit `e2e76c33` (accessibility descriptions, 2026-07-16) dropped that positional flag while adding `accessible_description`. The button fell through to `secondary-action` (outlined). The other three grid buttons were never destructive. Infrastructure's three actions still passed `True`.

Restored as `create_btn(..., True, accessible_description=...)`. `test_basic_repair_buttons_wired` now requires `destructive-action` on `btn_ip` only.

## What was verified

| Check | Result |
| --- | --- |
| `pytest tests/test_theme.py tests/test_ai_console_overlay.py tests/test_ui_elements_wiring.py` | passed (theme 4, overlay+wiring 24, then the Renew IP wiring tests) |
| Xvfb render, light Adwaita, before vs after the stack/`text` rules | white page fill and white log gone |
| Realized `MainWindow`, palette closed | revealer unmapped; `set_current_page(1)` shows VPN Not Installed |

Not verified on a physical dock launch. Restart NetMedic from the dock after these changes. Ctrl+Space must still open the palette; that path calls `show()` before reveal.
