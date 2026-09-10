import gi
import logging
import threading
import concurrent.futures
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from concurrent.futures import ThreadPoolExecutor

MAX_LOG_LINES = 500

from netmedic.network import NetworkMedic
from netmedic.operators.wifi import WifiOperator
from netmedic.models import NetResult, TaskResult
from netmedic.ui_vpn import VPNPanel  # Nuevo panel modular
from netmedic.theme import apply_theme
from netmedic.ai_console import AIConsoleController
from netmedic.gui_actions import GuiActionBridge
from netmedic.integration import shutdown_operators
from netmedic.teardown import register as register_teardown
from . import __version__
from netmedic.paths import resolve_app_icon_path, resolve_manual_path

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="NetMedic Linux - Professional")
        self.is_destroyed = False
        self._apply_window_icon()
        apply_theme()
        self.medic = NetworkMedic()
        self.wifi_op = WifiOperator()
        # Privileged/safe repair actions go through IPC (auth + audit).
        self.actions = GuiActionBridge()
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._log_lock = threading.Lock()
        self._busy_count = 0
        self._busy_lock = threading.Lock()
        
        self.set_default_size(500, 650) # Un poco más alto para acomodar el panel VPN
        self.set_border_width(10)
        self.connect("destroy", self.on_destroy)

        self._root_overlay = Gtk.Overlay()
        self.add(self._root_overlay)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._root_overlay.add(main_box)

        # 1. Header
        header = Gtk.HeaderBar(title="NetMedic", subtitle="Network Repair Tool")
        header.set_show_close_button(True)
        self.set_titlebar(header)

        # Donation Button (Buy Me a Coffee)
        btn_donate = Gtk.Button()
        btn_donate_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_donate_icon = Gtk.Image.new_from_icon_name("emblem-favorite-symbolic", Gtk.IconSize.BUTTON)
        btn_donate_label = Gtk.Label(label="Support")
        btn_donate_box.pack_start(btn_donate_icon, False, False, 0)
        btn_donate_box.pack_start(btn_donate_label, False, False, 0)
        btn_donate.add(btn_donate_box)
        
        # A11Y: Donate
        a11y_donate = btn_donate.get_accessible()
        a11y_donate.set_name("Support Kayab Software")
        a11y_donate.set_description("Opens a browser to support Kayab Software development")
        
        btn_donate.set_tooltip_text("Support Kayab Software development")
        btn_donate.connect("clicked", self.on_donate)
        header.pack_end(btn_donate)

        # About Menu Item (contextual access)
        btn_about = Gtk.Button.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON)
        
        # A11Y: About
        a11y_about = btn_about.get_accessible()
        a11y_about.set_name("About NetMedic")
        a11y_about.set_description("Shows information about this application")
        
        btn_about.connect("clicked", self.on_about)
        header.pack_end(btn_about)

        # 2. Notebook for Tabs (Hierarchical UI)
        self.notebook = Gtk.Notebook()
        main_box.pack_start(self.notebook, True, True, 0)
        notebook = self.notebook

        # --- TAB 1: BASIC REPAIR (Safe & Automated) ---
        basic_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        basic_box.set_border_width(20)
        basic_box.get_style_context().add_class("surface-card")
        
        self.repair_btn = Gtk.Button()
        self.repair_btn.set_label("SMART REPAIR (Safe)")
        self.repair_btn.get_style_context().add_class("primary-action")
        
        # A11Y: Smart Repair
        a11y_repair = self.repair_btn.get_accessible()
        a11y_repair.set_name("Run Smart Repair")
        a11y_repair.set_description("Executes non-destructive network diagnostics, DNS flush and IP renewal automatically")
        
        self.repair_btn.connect("clicked", self.on_smart_repair)
        basic_box.pack_start(self.repair_btn, False, False, 0)
        
        basic_info = Gtk.Label(label="Runs non-destructive diagnostics, DNS flush and IP renewal.")
        basic_info.set_line_wrap(True)
        basic_box.pack_start(basic_info, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_halign(Gtk.Align.CENTER)
        
        self.btn_diag = self.create_btn("Check Connectivity", self.on_diagnostics, accessible_description="Test internet connectivity")
        self.btn_dns = self.create_btn("Flush DNS", self.on_flush_dns, accessible_description="Clear local DNS cache")
        self.btn_ip = self.create_btn("Renew IP Address", self.on_renew_ip, accessible_description="Request new IP from DHCP server")
        self.btn_wifi = self.create_btn("Scan Wi-Fi Congestion", self.on_scan_wifi, accessible_description="Analyze local Wi-Fi channel congestion")
        
        grid.attach(self.btn_diag, 0, 0, 1, 1)
        grid.attach(self.btn_dns, 1, 0, 1, 1)
        grid.attach(self.btn_ip, 0, 1, 1, 1)
        grid.attach(self.btn_wifi, 1, 1, 1, 1)
        
        basic_box.pack_start(grid, False, False, 10)
        notebook.append_page(basic_box, Gtk.Label(label="Basic Repair"))

        # --- TAB 2: INFRASTRUCTURE (Privileged & Disruptive) ---
        adv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        adv_box.set_border_width(15)
        adv_box.get_style_context().add_class("surface-card")
        
        adv_warn = Gtk.Label(label="These actions modify system network configuration.")
        adv_warn.get_style_context().add_class("warning-text")
        adv_box.pack_start(adv_warn, False, False, 0)

        # 2.1. System Actions Frame
        sys_frame = Gtk.Frame()
        sys_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        sys_box.set_border_width(10)
        
        self.btn_stack = self.create_btn(
            "Reset TCP/IP Stack", self.on_reset_tcp_ip, True,
            accessible_description="Restart NetworkManager; disconnects all interfaces briefly",
        )
        self.btn_adapter = self.create_btn(
            "Cycle Network Adapter", self.on_restart_adapter, True,
            accessible_description="Bring default network interface down and up",
        )
        self.btn_firewall = self.create_btn(
            "Toggle Firewall (UFW)", self.on_toggle_firewall, True,
            accessible_description="Enable or disable the UFW firewall",
        )
        
        sys_box.pack_start(self.btn_stack, False, False, 0)
        sys_box.pack_start(self.btn_adapter, False, False, 0)
        sys_box.pack_start(self.btn_firewall, False, False, 0)
        sys_frame.add(sys_box)
        
        adv_box.pack_start(sys_frame, False, False, 0)

        # 2.2. VPN Infrastructure Panel (Modular)
        # Pasamos el executor y métodos de feedback de la ventana principal
        self.vpn_panel = VPNPanel(
            executor=self.executor,
            log_callback=self.append_log,
            set_busy_callback=self.set_busy,
            main_window=self,
        )
        adv_box.pack_start(self.vpn_panel, True, True, 0)
            
        notebook.append_page(adv_box, Gtk.Label(label="Infrastructure"))
        notebook.connect("switch-page", self._on_tab_switch)

        # 3. Log Area
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(100) # Reducido un poco para dar espacio a VPN
        self.log_view = Gtk.TextView()
        self.log_view.get_style_context().add_class("log-view")
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        scrolled.add(self.log_view)
        main_box.pack_start(scrolled, False, True, 0)
        
        # 4. Footer (Status + Spinner)
        footer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        
        self.status_bar = Gtk.Statusbar()
        self.status_context = self.status_bar.get_context_id("main")
        self._status_message_id = self.status_bar.push(self.status_context, "System Ready")
        
        self.spinner = Gtk.Spinner()
        
        footer_box.pack_start(self.status_bar, True, True, 0)
        footer_box.pack_end(self.spinner, False, False, 5)
        
        main_box.pack_end(footer_box, False, False, 0)

        self.ai_console = AIConsoleController(self)
        self.ai_console.mount(self._root_overlay)
        register_teardown(self.emergency_shutdown)
        # Non-blocking install health note (helper / polkit).
        GLib.idle_add(self._report_install_health)

    def _report_install_health(self):
        """Append one log line if privileged path is not production-ready."""
        try:
            from netmedic.status import collect_status

            report = collect_status()
            if report.get("production_ready"):
                self.append_log(
                    f"Install health: OK (helper={'on' if report.get('helper_mode') else 'off'})"
                )
            else:
                self.append_log(
                    "Install health: incomplete — run `netmedic --status` "
                    "and ./scripts/install-polkit-policy.sh if needed."
                )
                for hint in report.get("hints") or []:
                    self.append_log(f"  hint: {hint}")
        except Exception as exc:
            logging.debug("Install health check skipped: %s", exc)
        return False

    def _on_tab_switch(self, notebook, page, page_num):
        """Defer VPN refresh until Infrastructure tab is first shown."""
        if page_num == 1 and hasattr(self, "vpn_panel"):
            if not self.vpn_panel._state_loaded or self.vpn_panel._needs_retry:
                self.vpn_panel.refresh_state()

    def create_btn(self, label, handler, destructive=False, accessible_name=None, accessible_description=None):
        btn = Gtk.Button(label=label)
        if destructive:
            btn.get_style_context().add_class("destructive-action")
        else:
            btn.get_style_context().add_class("secondary-action")
        
        # A11Y support
        a11y = btn.get_accessible()
        a11y.set_name(accessible_name or label)
        if accessible_description:
            a11y.set_description(accessible_description)
            
        btn.connect("clicked", handler)
        return btn

    def set_busy(self, busy, msg="Processing..."):
        """Reference-counted busy state. Multiple subsystems can overlap."""
        with self._busy_lock:
            if busy:
                self._busy_count += 1
                if self._busy_count == 1:
                    GLib.idle_add(lambda: self._update_busy_ui(True, msg))
            else:
                self._busy_count = max(0, self._busy_count - 1)
                if self._busy_count == 0:
                    GLib.idle_add(lambda: self._update_busy_ui(False, msg))

    def _update_busy_ui(self, busy, msg):
        """Thread-safe UI update for busy state."""
        if getattr(self, "is_destroyed", False):
            return False
        if self._status_message_id:
            self.status_bar.pop(self.status_context)
        self._status_message_id = self.status_bar.push(
            self.status_context, msg if busy else "System Ready"
        )
        action_buttons = (
            getattr(self, "btn_diag", None),
            getattr(self, "btn_dns", None),
            getattr(self, "btn_ip", None),
            getattr(self, "btn_wifi", None),
            getattr(self, "btn_stack", None),
            getattr(self, "btn_adapter", None),
            getattr(self, "btn_firewall", None),
            getattr(self, "repair_btn", None),
        )
        if busy:
            self.spinner.start()
            self.notebook.set_sensitive(False)
            for btn in action_buttons:
                if btn is not None:
                    btn.set_sensitive(False)
            if hasattr(self, "vpn_panel"):
                self.vpn_panel.set_sensitive(False)
        else:
            self.spinner.stop()
            self.notebook.set_sensitive(True)
            for btn in action_buttons:
                if btn is not None:
                    btn.set_sensitive(True)
            if hasattr(self, "vpn_panel"):
                self.vpn_panel.set_sensitive(True)
        if hasattr(self, "ai_console"):
            self.ai_console.set_sensitive(not busy)
        return False

    def ask_confirmation(self, title, message):
        """Muestra un diálogo de confirmación modal."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=title,
        )
        dialog.format_secondary_text(message)
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def _apply_window_icon(self):
        icon_path = resolve_app_icon_path()
        if icon_path is not None:
            try:
                self.set_icon_from_file(str(icon_path))
                return
            except GLib.Error:
                logging.debug("Failed to load icon from %s", icon_path, exc_info=True)
        self.set_icon_name("netmedic")

    def emergency_shutdown(self, *, wait_for_executor: bool = False):
        if getattr(self, "_emergency_done", False):
            return
        self._emergency_done = True
        self.is_destroyed = True
        try:
            self.executor.shutdown(wait=wait_for_executor, cancel_futures=True)
        except Exception as exc:
            logging.error("Executor shutdown failed: %s", exc)
        shutdown_operators([self.wifi_op, self.vpn_panel.operator])

    def on_destroy(self, widget):
        logging.info("Closing application. Running final cleanup...")
        self.emergency_shutdown(wait_for_executor=False)
        try:
            from netmedic.ipc_client import PilotClient
            PilotClient().shutdown()
        except Exception as exc:
            logging.debug("PilotClient shutdown skipped: %s", exc)
        # Best-effort iface cleanup before quitting (avoid silent daemon-thread loss).
        try:
            res = self.medic.cleanup()
            logging.info("Final cleanup: %s", res.message)
        except Exception as e:
            logging.error("Error in final cleanup: %s", e)
        Gtk.main_quit()

    def append_log(self, text):
        def _append():
            if getattr(self, "is_destroyed", False):
                return False
            with self._log_lock:
                buffer = self.log_view.get_buffer()
                buffer.insert(buffer.get_end_iter(), text + "\n")
                # Cap log to MAX_LOG_LINES to prevent memory growth
                line_count = buffer.get_line_count()
                if line_count > MAX_LOG_LINES:
                    start = buffer.get_start_iter()
                    excess_end = buffer.get_iter_at_line(line_count - MAX_LOG_LINES)
                    buffer.delete(start, excess_end)
                self.log_view.scroll_to_iter(buffer.get_end_iter(), 0, False, 0, 0)
            return False
        GLib.idle_add(_append)

    def run_async_task(self, task_func, msg="Running..."):
        self.set_busy(True, msg)
        def task_wrapper():
            try:
                return TaskResult(success=True, data=task_func())
            except Exception as e:
                return TaskResult(success=False, error=str(e))

        future = self.executor.submit(task_wrapper)
        future.add_done_callback(lambda f: self.on_task_done(f))

    def on_task_done(self, future):
        self.set_busy(False)
        try:
            from netmedic.models import ResultCode
            res = future.result()
            if res.success:  # TaskResult.success — not deprecated
                net_res = res.data
                self.append_log(net_res.to_log_entry())
                if net_res.details and not isinstance(net_res.details, dict):
                    pass
                
                # PR2: code-driven detection, not locale-sensitive substring
                code = net_res.code
                if isinstance(code, str):
                    try:
                        code = ResultCode(code)
                    except ValueError:
                        code = None
                if code in (ResultCode.FAILED, ResultCode.ERROR, ResultCode.CANCELLED, ResultCode.PARTIAL):
                    # Normalize string code
                    if isinstance(code, str):
                        try:
                            code = ResultCode(code)
                        except ValueError:
                            code = None
                    if code == ResultCode.CANCELLED:
                        self.append_log("⚠️ Operation cancelled by the user (missing privileges).")
                        GLib.idle_add(lambda: self._show_error_dialog(
                            "Authentication Required",
                            "This operation requires administrator privileges. "
                            "Please enter your password when prompted."
                        ))
                    elif code == ResultCode.ERROR and net_res.details and "helper-missing" in str(net_res.details).lower():
                        self.append_log("⚠️ Privileged helper not installed — run ./scripts/install-polkit-policy.sh then netmedic --status")
                        GLib.idle_add(lambda: self._show_error_dialog(
                            "Helper Not Installed",
                            "Privileged helper not installed.\n\n"
                            "Run: ./scripts/install-polkit-policy.sh (requires sudo)\n"
                            "Then: netmedic --status"
                        ))
                    else:
                        # Fallback text check for legacy payloads without code
                        text = (net_res.message + " " + str(net_res.details or "")).lower()
                        if "helper-missing" in text or "helper not installed" in text:
                            self.append_log("⚠️ Privileged helper not installed — run ./scripts/install-polkit-policy.sh then netmedic --status")
                            GLib.idle_add(lambda: self._show_error_dialog(
                                "Helper Not Installed",
                                "Privileged helper not installed.\n\n"
                                "Run: ./scripts/install-polkit-policy.sh (requires sudo)\n"
                                "Then: netmedic --status"
                            ))
                        elif any(w in text for w in ("cancel", "dismissed")):
                            self.append_log("⚠️ Operation cancelled by the user (missing privileges).")
                            GLib.idle_add(lambda: self._show_error_dialog(
                                "Authentication Required",
                                "This operation requires administrator privileges. "
                                "Please enter your password when prompted."
                            ))
            else:
                self.append_log(f"❌ System Error: {res.error}")
                GLib.idle_add(lambda: self._show_error_dialog("Unexpected Error", res.error))
        except concurrent.futures.CancelledError:
            self.append_log("⚠️ Task cancelled.")
        except Exception as e:
            self.append_log(f"❌ Fatal: {e}")
            logging.error("Error in on_task_done: %s", e, exc_info=True)

    def _show_error_dialog(self, title, message):
        """Shows a user-friendly error dialog."""
        if getattr(self, "is_destroyed", False): return
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    # --- Handlers ---

    def _ipc_action(self, action: str, params=None, *, confirmed=None):
        """Run a catalog action via IPC (worker-thread safe)."""
        return self.actions.call(action, params, confirmed=confirmed)

    def _wait_for_settle(self, iface: str | None, timeout: int = 8):
        """PR3: poll settle instead of blind sleep. Checks IP + NM activated state."""
        import time
        import logging
        from netmedic.system import CommandRunner
        start = time.monotonic()
        if not iface:
            # No iface to wait for; short sleep
            time.sleep(1)
            logging.info("settle: no iface, slept 1s")
            return
        for i in range(max(1, timeout)):
            # Check IPv4 present
            res = CommandRunner.run(["ip", "-4", "addr", "show", iface])
            has_ip = res.success and "inet " in (res.stdout or "")
            # Check NM device state activated (best-effort)
            nm = CommandRunner.run(["nmcli", "-t", "-f", "GENERAL.STATE", "device", "show", iface])
            nm_ok = nm.success and "activated" in (nm.stdout or "").lower()
            if has_ip and (nm_ok or not nm.success):
                # If nmcli not available, has_ip alone is enough
                logging.info("settle: iface %s ready after %ss (has_ip=%s nm_ok=%s)", iface, round(time.monotonic() - start, 2), has_ip, nm_ok)
                return
            time.sleep(1)
        logging.info("settle: iface %s timeout after %ss", iface, round(time.monotonic() - start, 2))
        # Timeout: don't fail, just proceed to post-check

    def on_smart_repair(self, _):
        # Privileged steps use IPC so polkit + audit cover the repair path.
        def sequence():
            from netmedic.models import ResultCode
            import os
            # POST_REPAIR_VERIFY flag (PR3) default ON
            do_verify = os.environ.get("NETMEDIC_POST_REPAIR_VERIFY", "1").lower() not in ("0", "false", "no")
            self.append_log("--- Starting Smart Repair ---")
            repair_ctx = self.status_bar.get_context_id("repair")
            diag_res = None
            repairs = []

            # Step 1: pre-repair diagnostics (informational, not counted as repair)
            GLib.idle_add(lambda: self.status_bar.push(repair_ctx, "Diagnosing..."))
            try:
                diag_res = self._ipc_action("network_status")
                self.append_log(diag_res.to_log_entry())
                if diag_res.details:
                    self.append_log(f"  ↳ {diag_res.details}")
            finally:
                GLib.idle_add(lambda: self.status_bar.pop(repair_ctx))

            # Structured skip check: no gateway => gateway_ok false
            skip_renew = False
            iface_for_settle = None
            if diag_res is not None:
                # PR2: use structured details/data, not substring
                if diag_res.data and isinstance(diag_res.data, dict):
                    skip_renew = not diag_res.data.get("gateway_ok", False)
                    iface_for_settle = diag_res.data.get("gateway") and None  # placeholder
                    # Prefer data gateway check; also extract iface from details if available
                    if diag_res.details and isinstance(diag_res.details, dict):
                        gw = diag_res.details.get("gateway")
                        skip_renew = gw in (None, "none") or not diag_res.details.get("gateway_ok", False)
                else:
                    skip_renew = "Gateway Not Found" in (diag_res.message or "")  # sf-str: allow legacy compat for payloads without details.code
                # Also try to get default iface for settle wait
                try:
                    from netmedic.network import NetworkMedic
                    iface_for_settle = NetworkMedic().get_default_interface()
                except Exception:
                    iface_for_settle = None
            if skip_renew:
                self.append_log(
                    "Smart Repair: skipping IP renewal (no default gateway detected)."
                )

            # R4 short-circuit: if network already healthy, don't elevate
            is_healthy = False
            if diag_res and diag_res.data and isinstance(diag_res.data, dict):
                is_healthy = bool(diag_res.data.get("gateway_ok") and diag_res.data.get("dns_ok") and diag_res.data.get("internet_ok"))
            elif diag_res:
                # Fallback to code OK
                try:
                    from netmedic.models import ResultCode as _RC
                    is_healthy = diag_res.code == _RC.OK
                except Exception:
                    is_healthy = diag_res.success
            if is_healthy:
                self.append_log("Smart Repair: network healthy, nothing to repair — skipped privileged actions.")
                # No repairs needed; still optionally verify post (should remain OK)
                if do_verify:
                    GLib.idle_add(lambda: self.status_bar.push(repair_ctx, "Verifying repair..."))
                    try:
                        post_res = self._ipc_action("network_status")
                        self.append_log(f"[Post-Repair] {post_res.to_log_entry()}")
                    finally:
                        GLib.idle_add(lambda: self.status_bar.pop(repair_ctx))
                else:
                    post_res = None
                from netmedic.models import ResultCode as _RC2
                return NetResult("Smart Repair", False, "SKIPPED — network healthy, nothing to repair", data={"pre": diag_res.data if diag_res else None, "post": post_res.data if post_res else None}, code=_RC2.SKIPPED)

            # Step 2: flush DNS (always) — EXECUTED expected
            GLib.idle_add(lambda: self.status_bar.push(repair_ctx, "Flushing DNS..."))
            try:
                res = self._ipc_action("flush_dns")
                repairs.append(res)
                self.append_log(res.to_log_entry())
                if res.details:
                    self.append_log(f"  ↳ {res.details}")
            finally:
                GLib.idle_add(lambda: self.status_bar.pop(repair_ctx))

            # Step 3: renew IP (conditionally)
            if not skip_renew:
                GLib.idle_add(lambda: self.status_bar.push(repair_ctx, "Renewing IP..."))
                try:
                    res = self._ipc_action("renew_ip")
                    repairs.append(res)
                    self.append_log(res.to_log_entry())
                    if res.details:
                        self.append_log(f"  ↳ {res.details}")
                finally:
                    GLib.idle_add(lambda: self.status_bar.pop(repair_ctx))

            # Step 4: post-repair verification
            if do_verify:
                GLib.idle_add(lambda: self.status_bar.push(repair_ctx, "Verifying repair..."))
                try:
                    # PR3 settle poll, not blind sleep
                    self._wait_for_settle(iface_for_settle, timeout=8)
                    post_res = self._ipc_action("network_status")
                    self.append_log(f"[Post-Repair] {post_res.to_log_entry()}")
                    if post_res.details:
                        self.append_log(f"  ↳ {post_res.details}")
                        if isinstance(post_res.details, dict) and post_res.details.get("captive_portal_hint"):
                            self.append_log(f"  ↳ Hint: {post_res.details.get('captive_portal_hint')}")
                finally:
                    GLib.idle_add(lambda: self.status_bar.pop(repair_ctx))
            else:
                # Verification disabled — treat as unknown
                post_res = None

            # Distinguish repair execution vs network recovery with delta (PR3) — code-driven
            from netmedic.models import ResultCode as _RC2
            def _is_ok_or_executed(r):
                c = r.code
                if isinstance(c, str):
                    try:
                        c = _RC2(c)
                    except ValueError:
                        return False
                return c in (_RC2.OK, _RC2.EXECUTED)
            repairs_ok = all(_is_ok_or_executed(r) for r in repairs) if repairs else True
            repairs_total = len(repairs)
            repairs_succeeded = sum(1 for r in repairs if _is_ok_or_executed(r))
            # pre/post healthy means code OK (not PARTIAL/FAILED)
            pre_ok = (diag_res.code == _RC2.OK) if diag_res and diag_res.code else False
            post_ok = (post_res.code == _RC2.OK) if post_res and post_res.code else False
            # Extract per-target booleans for delta
            pre_dns = (diag_res.data or {}).get("dns_ok") if diag_res and diag_res.data else None
            pre_net = (diag_res.data or {}).get("internet_ok") if diag_res and diag_res.data else None
            post_dns = (post_res.data or {}).get("dns_ok") if post_res and post_res.data else None
            post_net = (post_res.data or {}).get("internet_ok") if post_res and post_res.data else None
            # PR2: code-driven overall
            if not do_verify:
                # Debug escape hatch only. Never present unverified repairs as OK/✅.
                overall_code = ResultCode.EXECUTED if repairs_ok else ResultCode.FAILED
                summary = (
                    f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} executed; "
                    "post-repair verification DISABLED "
                    "(NETMEDIC_POST_REPAIR_VERIFY=0, debug only). "
                    "Re-run with the flag unset before treating this as recovery."
                )
                overall = False
            elif repairs_ok and post_ok:
                if not pre_ok:
                    summary = f"Smart Repair: SUCCESS (verified) — repairs {repairs_succeeded}/{repairs_total} ok | pre=FAIL post=OK"
                else:
                    summary = f"Smart Repair finished: all {repairs_total} repairs succeeded — network still healthy | pre=OK post=OK"
                overall = True
                overall_code = ResultCode.OK
            elif repairs_ok and not post_ok:
                # Partial recovery detection
                if post_dns and not post_net:
                    summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} executed; network NOT recovered. Gateway OK, WAN down → likely upstream/ISP/captive portal. Suggestions: check router uplink, or run manual probes (MANUAL §Troubleshooting). | pre={'OK' if pre_ok else 'FAIL'} post=FAIL"
                    overall_code = ResultCode.PARTIAL
                elif post_dns is False and post_net is False and pre_dns is False and pre_net is False:
                    summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} executed; network NOT recovered. Gateway OK, WAN down → likely upstream/ISP/captive portal. | pre=FAIL post=FAIL"
                    overall_code = ResultCode.FAILED
                elif not pre_ok and post_ok is False:
                    summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} ok — network still down (upstream outage suspected) | pre=FAIL post=FAIL"
                    overall_code = ResultCode.FAILED
                else:
                    summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} ok — new fault detected post-repair | pre={'OK' if pre_ok else 'FAIL'} post=FAIL"
                    overall_code = ResultCode.FAILED
                overall = False
            else:
                summary = f"Smart Repair: repairs {repairs_succeeded}/{repairs_total} succeeded — review log for failures | pre={'OK' if pre_ok else 'FAIL'} post={'OK' if post_ok else 'FAIL'}"
                overall = False
                overall_code = ResultCode.FAILED
            return NetResult("Smart Repair", overall, summary, data={"pre": diag_res.data if diag_res else None, "post": post_res.data if post_res else None, "repairs_ok": repairs_ok}, code=overall_code)

        self.run_async_task(sequence, "Repairing Network...")

    def on_diagnostics(self, _):
        self.run_async_task(lambda: self._ipc_action("network_status"), "Diagnosing...")

    def on_flush_dns(self, _):
        self.run_async_task(lambda: self._ipc_action("flush_dns"), "Flushing DNS...")

    def on_renew_ip(self, _):
        self.run_async_task(lambda: self._ipc_action("renew_ip"), "Renewing IP...")

    def on_scan_wifi(self, _):
        self.run_async_task(lambda: self._ipc_action("wifi_diagnostics"), "Scanning Wi-Fi...")

    # --- Dangerous Handlers (Protected) ---

    def on_reset_tcp_ip(self, _):
        if self.ask_confirmation(
            "Reset TCP/IP Stack?",
            "This will restart NetworkManager. You will lose connection momentarily.",
        ):
            self.run_async_task(
                lambda: self._ipc_action("reset_tcp_ip_stack"),
                "Resetting Stack...",
            )

    def on_restart_adapter(self, _):
        if self.ask_confirmation(
            "Restart Network Adapter?",
            "The default interface will be brought DOWN and then UP. SSH connections may drop.",
        ):
            self.run_async_task(
                lambda: self._ipc_action("restart_adapter"),
                "Restarting Adapter...",
            )

    def on_toggle_firewall(self, _):
        if self.ask_confirmation(
            "Toggle Firewall?",
            "Changing firewall rules may expose your system or block connections.",
        ):
            self.run_async_task(
                lambda: self._ipc_action("toggle_firewall"),
                "Toggling Firewall...",
            )

    def _spawn_browser(self, url: str):
        import subprocess
        try:
            proc = subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            GLib.child_watch_add(proc.pid, lambda _pid, _status: None)
        except Exception as e:
            logging.error("Failed to open URL %s: %s", url, e)

    def on_donate(self, _):
        self._spawn_browser("https://buymeacoffee.com/kayabsoftware")

    def on_about(self, _):
        about = Gtk.AboutDialog()
        about.set_program_name("NetMedic Linux")
        about.set_version(__version__)
        about.set_comments("Sovereign Runtime Network Manager.\n\nRead the Manual to learn more.")
        about.set_license_type(Gtk.License.MIT_X11)

        manual = resolve_manual_path()
        if manual is not None:
            about.set_website("file://" + str(manual))
            about.set_website_label("User Manual")
        
        # Enlace a soporte
        # Gtk.AboutDialog no permite múltiples sitios web fácilmente, 
        # así que añadimos un botón de soporte en el diálogo
        btn_support = Gtk.Button(label="Support Kayab Software")
        btn_support.connect("clicked", lambda b: self.on_donate(None))
        about.get_content_area().pack_start(btn_support, False, False, 5)
        
        about.run()
        about.destroy()
