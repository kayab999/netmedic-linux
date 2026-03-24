import gi
import logging
import threading
import concurrent.futures
import traceback
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from concurrent.futures import ThreadPoolExecutor

from netmedic.network import NetworkMedic
from netmedic.operators.wifi import WifiOperator
from netmedic.models import NetResult, TaskResult
from netmedic.ui_vpn import VPNPanel  # Nuevo panel modular
from netmedic.theme import apply_theme

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="NetMedic Linux - Professional")
        self.is_destroyed = False
        self.set_icon_name("netmedic")
        apply_theme()
        self.medic = NetworkMedic()
        self.wifi_op = WifiOperator()
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._log_lock = threading.Lock()
        
        self.set_default_size(500, 650) # Un poco más alto para acomodar el panel VPN
        self.set_border_width(10)
        self.connect("destroy", self.on_destroy)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(main_box)

        # 1. Header
        header = Gtk.HeaderBar(title="NetMedic", subtitle="Network Repair Tool")
        header.set_show_close_button(True)
        self.set_titlebar(header)

        # 2. Notebook for Tabs (Hierarchical UI)
        notebook = Gtk.Notebook()
        main_box.pack_start(notebook, True, True, 0)

        # --- TAB 1: BASIC REPAIR (Safe & Automated) ---
        basic_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        basic_box.set_border_width(20)
        basic_box.get_style_context().add_class("surface-card")
        
        repair_btn = Gtk.Button()
        repair_btn.set_label("SMART REPAIR (Safe)")
        repair_btn.get_style_context().add_class("primary-action")
        repair_btn.connect("clicked", self.on_smart_repair)
        basic_box.pack_start(repair_btn, False, False, 0)
        
        basic_info = Gtk.Label(label="Runs non-destructive diagnostics, DNS flush and IP renewal.")
        basic_info.set_line_wrap(True)
        basic_box.pack_start(basic_info, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_halign(Gtk.Align.CENTER)
        
        self.btn_diag = self.create_btn("Check Connectivity", self.on_diagnostics)
        self.btn_dns = self.create_btn("Flush DNS", self.on_flush_dns)
        self.btn_ip = self.create_btn("Renew IP Address", self.on_renew_ip, True)
        self.btn_wifi = self.create_btn("Scan Wi-Fi Congestion", self.on_scan_wifi)
        
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
        
        self.btn_stack = self.create_btn("Reset TCP/IP Stack", self.on_reset_tcp_ip, True)
        self.btn_adapter = self.create_btn("Cycle Network Adapter", self.on_restart_adapter, True)
        self.btn_firewall = self.create_btn("Toggle Firewall (UFW)", self.on_toggle_firewall, True)
        
        sys_box.pack_start(self.btn_stack, False, False, 0)
        sys_box.pack_start(self.btn_adapter, False, False, 0)
        sys_box.pack_start(self.btn_firewall, False, False, 0)
        sys_frame.add(sys_box)
        
        adv_box.pack_start(sys_frame, False, False, 0)

        # 2.2. VPN Infrastructure Panel (Modular)
        # Pasamos el executor y métodos de feedback de la ventana principal
        self.vpn_panel = VPNPanel(
            executor=self.executor,
            log_callback=self.append_log, # Usamos el método interno que ya es thread-safe
            set_busy_callback=self.set_busy
        )
        adv_box.pack_start(self.vpn_panel, True, True, 0)
            
        notebook.append_page(adv_box, Gtk.Label(label="Infrastructure"))

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
        self.status_bar.push(self.status_context, "System Ready")
        
        self.spinner = Gtk.Spinner()
        
        footer_box.pack_start(self.status_bar, True, True, 0)
        footer_box.pack_end(self.spinner, False, False, 5)
        
        main_box.pack_end(footer_box, False, False, 0)

    def create_btn(self, label, handler, destructive=False):
        btn = Gtk.Button(label=label)
        if destructive:
            btn.get_style_context().add_class("destructive-action")
        else:
            btn.get_style_context().add_class("secondary-action")
        btn.connect("clicked", handler)
        return btn

    def set_busy(self, busy, msg="Processing..."):
        GLib.idle_add(lambda: self._update_busy_ui(busy, msg))

    def _update_busy_ui(self, busy, msg):
        """Thread-safe UI update for busy state"""
        if getattr(self, "is_destroyed", False):
            return False
        self.status_bar.push(self.status_context, msg if busy else "System Ready")
        if busy:
            self.spinner.start()
            # Bloqueamos tabs para evitar condiciones de carrera entre paneles
            # (Futura mejora: bloquear solo panel activo)
        else:
            self.spinner.stop()
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

    def on_destroy(self, widget):
        logging.info("Closing application. Running final cleanup...")
        self.is_destroyed = True
        self.executor.shutdown(wait=True, cancel_futures=True)
        
        try:
            # Al ser singleton, recuperamos la instancia con las interfaces creadas
            res = self.medic.cleanup()
            logging.info(f"Final cleanup: {res.message}")
        except Exception as e:
            logging.error(f"Error in final cleanup: {e}")
        
        Gtk.main_quit()

    def append_log(self, text):
        def _append():
            if getattr(self, "is_destroyed", False):
                return False
            with self._log_lock:
                buffer = self.log_view.get_buffer()
                buffer.insert(buffer.get_end_iter(), text + "\n")
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
        GLib.idle_add(lambda: self.set_busy(False))
        try:
            res = future.result()
            if res.success:
                net_res = res.data
                self.append_log(net_res.to_log_entry())
                
                # Feedback específico para elevación cancelada
                if not net_res.success and "cancelada" in net_res.message.lower():
                    self.append_log("⚠️ Operación cancelada por el usuario (Falta de privilegios).")
                    GLib.idle_add(lambda: self._show_error_dialog(
                        "Autenticación Requerida", 
                        "La operación necesita privilegios de administrador. "
                        "Por favor, introduzca su contraseña cuando se le solicite."
                    ))
            else:
                self.append_log(f"❌ Error del Sistema: {res.error}")
                GLib.idle_add(lambda: self._show_error_dialog("Error Inesperado", res.error))
        except concurrent.futures.CancelledError:
            self.append_log("⚠️ Tarea cancelada.")
        except Exception as e:
            self.append_log(f"❌ Fatal: {e}")
            logging.error(f"Error in on_task_done: {e}", exc_info=True)

    def _show_error_dialog(self, title, message):
        """Muestra un diálogo de error amigable."""
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

    def on_smart_repair(self, _):
        # No confirmation needed for safe repair
        def sequence():
            self.append_log("--- Starting Smart Repair ---")
            steps = [
                (self.medic.run_diagnostics, "Diagnosing..."),
                (self.medic.flush_dns, "Flushing DNS..."),
                (self.medic.renew_ip, "Renewing IP...")
            ]
            all_ok = True
            for step_func, step_msg in steps:
                GLib.idle_add(lambda m=step_msg: self.status_bar.push(self.status_context, m))
                res = step_func()
                self.append_log(res.to_log_entry())
                if not res.success:
                    all_ok = False
                    break
            return NetResult("Smart Repair", all_ok, "Sequence finished" if all_ok else "Sequence stopped due to failure")
            
        self.run_async_task(sequence, "Repairing Network...")

    def on_diagnostics(self, _): self.run_async_task(self.medic.run_diagnostics, "Diagnosing...")
    def on_flush_dns(self, _): self.run_async_task(self.medic.flush_dns, "Flushing DNS...")
    def on_renew_ip(self, _): self.run_async_task(self.medic.renew_ip, "Renewing IP...")
    def on_scan_wifi(self, _): self.run_async_task(self.wifi_op.scan_congestion, "Scanning Wi-Fi...")

    # --- Dangerous Handlers (Protected) ---

    def on_reset_tcp_ip(self, _): 
        if self.ask_confirmation("Reset TCP/IP Stack?", "This will restart NetworkManager. You will lose connection momentarily."):
            self.run_async_task(self.medic.reset_tcp_ip_stack, "Resetting Stack...")

    def on_restart_adapter(self, _): 
        if self.ask_confirmation("Restart Network Adapter?", "The default interface will be brought DOWN and then UP. SSH connections may drop."):
            self.run_async_task(self.medic.restart_adapter, "Restarting Adapter...")

    def on_toggle_firewall(self, _): 
        if self.ask_confirmation("Toggle Firewall?", "Changing firewall rules may expose your system or block connections."):
            self.run_async_task(self.medic.toggle_firewall, "Toggling Firewall...")
