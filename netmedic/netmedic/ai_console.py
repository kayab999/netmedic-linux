import json
from gi.repository import Gtk, GLib
from .ipc_client import PilotClient
from .sensors import get_network_snapshot
import logging

class AIConsoleController:
    def __init__(self, main_window):
        self.main_window = main_window
        self.client = PilotClient()
        self.overlay = None
        self.revealer = None
        self.entry = None
        self.preview_box = None

    def mount(self, overlay: Gtk.Overlay):
        """Attaches the AI command palette as an overlay on the main window."""
        self.overlay = overlay

        self.revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE, transition_duration=200)
        self.overlay.add_overlay(self.revealer)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(20)
        box.set_margin_start(40)
        box.set_margin_end(40)

        self.entry = Gtk.Entry(placeholder_text="Ej: 'Cambia DNS a Cloudflare' o 'Reinicia VPN'")
        self.entry.connect("activate", self._on_user_command)
        box.pack_start(self.entry, False, False, 0)

        self.preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.pack_start(self.preview_box, False, False, 0)

        self.revealer.add(box)
        self.revealer.set_reveal_child(False)

        accel_group = Gtk.AccelGroup()
        self.main_window.add_accel_group(accel_group)
        key, mod = Gtk.accelerator_parse("<Control>space")
        accel_group.connect(key, mod, Gtk.AccelFlags.VISIBLE, self._toggle_palette)

    def _toggle_palette(self, *args):
        revealed = self.revealer.get_reveal_child()
        self.revealer.set_reveal_child(not revealed)
        if not revealed:
            self.entry.grab_focus()
            for child in self.preview_box.get_children():
                self.preview_box.remove(child)
        return True

    def _on_user_command(self, entry):
        user_input = entry.get_text().strip()
        if not user_input:
            return

        snapshot = get_network_snapshot()

        self.client.ask(
            action="user_intent",
            params={"user_request": user_input, "network_state": snapshot},
            callback=self._handle_pilot_response
        )

        for child in self.preview_box.get_children():
            self.preview_box.remove(child)

        loading = Gtk.Label(label="Analyzing request…")
        loading.set_margin_top(8)
        self.preview_box.pack_start(loading, False, False, 0)
        self.preview_box.show_all()

    @staticmethod
    def _escape_markup(value) -> str:
        return GLib.markup_escape_text(str(value))

    def _translate_to_human(self, action, params):
        translations = {
            "vpn_reconnect": (
                "Restart the OpenVPN tunnel service "
                f"({self._escape_markup(params.get('interface', 'system'))})."
            ),
            "change_dns": (
                "Redirect DNS resolution to "
                f"{self._escape_markup(params.get('server', 'the specified server'))}."
            ),
            "network_status": "Run a full network diagnostics scan.",
            "wifi_diagnostics": "Analyze Wi-Fi spectrum for less congested channels.",
            "donate": "Open the Kayab Software support page in your browser.",
        }
        return translations.get(action, f"Execute the <b>{self._escape_markup(action)}</b> operation.")

    def _handle_pilot_response(self, result):
        if result.get("status") == "error":
            self._show_error_card(result.get("message", "Fallo de inferencia."))
            return

        action = result.get("action")
        params = result.get("params", {})
        
        human_explanation = self._translate_to_human(action, params)

        preview = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(15)
        box.set_margin_bottom(15)
        box.set_margin_start(20)
        box.set_margin_end(20)

        header_label = Gtk.Label(xalign=0)
        header_label.set_markup("<span foreground='#3498db'><b>🤖 AI Proposal:</b></span>")
        box.pack_start(header_label, False, False, 0)

        explanation_label = Gtk.Label(xalign=0)
        explanation_label.set_markup(human_explanation)
        explanation_label.set_line_wrap(True)
        box.pack_start(explanation_label, False, False, 0)

        technical_label = Gtk.Label(xalign=0)
        technical_label.set_markup(
            f"<span size='small' foreground='gray'>Target Tool: <tt>{self._escape_markup(action)}</tt></span>"
        )
        box.pack_start(technical_label, False, False, 0)

        btn_box = Gtk.Box(spacing=10)
        btn_box.set_margin_top(10)
        
        execute_btn = Gtk.Button(label="Authorize and Run")
        execute_btn.connect("clicked", lambda b: self._confirm_and_execute(action, params))

        cancel_btn = Gtk.Button(label="Dismiss")
        cancel_btn.connect("clicked", lambda b: self.revealer.set_reveal_child(False))

        btn_box.pack_start(execute_btn, True, True, 0)
        btn_box.pack_start(cancel_btn, True, True, 0)
        box.pack_start(btn_box, False, False, 0)

        preview.add(box)
        self.preview_box.pack_start(preview, False, False, 0)
        self.preview_box.show_all()

    def _show_error_card(self, message):
        preview = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin(12)
        
        err_label = Gtk.Label(xalign=0)
        err_label.set_markup(
            f"<span foreground='#e74c3c'><b>⚠️ Warning:</b></span>\n{self._escape_markup(message)}"
        )
        box.pack_start(err_label, False, False, 0)
        
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda b: self.revealer.set_reveal_child(False))
        box.pack_start(close_btn, False, False, 0)
        
        preview.add(box)
        self.preview_box.pack_start(preview, False, False, 0)
        self.preview_box.show_all()

    def _confirm_and_execute(self, action, params):
        self.revealer.set_reveal_child(False)

        if action == "donate":
            import subprocess
            try:
                subprocess.Popen(
                    ["xdg-open", "https://buymeacoffee.com/kayabsoftware"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as exc:
                logging.error("Failed to open donation URL: %s", exc)
            return

        def on_result(result):
            logging.info("Resultado final: %s", result)
            if hasattr(self.main_window, "append_log"):
                if result.get("status") == "error":
                    self.main_window.append_log(f"❌ AI [{action}]: {result.get('message', 'Error')}")
                else:
                    msg = result.get("message") or result.get("data") or "Completado"
                    self.main_window.append_log(f"🤖 AI [{action}]: {msg}")

        self.client.ask(action, params, on_result, confirmed=True)
