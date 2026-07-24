import gi
import logging
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from netmedic.operators.vpn.angristan import AngristanOperator
from netmedic.operators.base import OperatorStatus
from netmedic.models import NetResult, TaskResult
from netmedic.gui_actions import GuiActionBridge

class VPNPanel(Gtk.Box):
    def __init__(self, executor, log_callback=None, set_busy_callback=None, main_window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_border_width(10)
        
        self.executor = executor
        self.log_cb = log_callback
        self.set_busy_cb = set_busy_callback
        self.main_window = main_window
        self.operator = AngristanOperator()
        # All VPN catalog ops go through IPC (auth + audit); operator kept for teardown.
        self.actions = GuiActionBridge()
        self._state_loaded = False
        self._needs_retry = False
        
        # --- UI Components ---
        
        # 1. Header (Status & Main Action)
        self.header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.status_label = Gtk.Label(label="VPN Status: Checking...")
        self.status_label.get_style_context().add_class("header-text")
        
        self.action_btn = Gtk.Button(label="Action")
        # A11Y: Header Action
        a11y_action = self.action_btn.get_accessible()
        a11y_action.set_name("VPN Main Action")
        a11y_action.set_description("Performs main action, e.g., Install VPN or Check Status")
        
        self.action_btn.connect("clicked", self.on_main_action)
        self.action_btn.set_sensitive(False) # Disabled until check
        
        self.header_box.pack_start(self.status_label, False, False, 0)
        self.header_box.pack_end(self.action_btn, False, False, 0)
        
        self.add(self.header_box)
        self.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # 2. Client List Area
        self.clients_frame = Gtk.Frame(label="VPN Clients")
        self.clients_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.clients_box.set_border_width(10)
        
        # Client list with Stack for Empty State
        self.client_stack = Gtk.Stack()
        self.client_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(150)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.client_list_store = Gtk.ListStore(str, str, str) # Name, Status, Color
        self.tree_view = Gtk.TreeView(model=self.client_list_store)
        
        # Col 1: Name
        renderer_name = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn("Name", renderer_name, text=0)
        self.tree_view.append_column(col_name)
        
        # Col 2: Status
        renderer_status = Gtk.CellRendererText()
        col_status = Gtk.TreeViewColumn("Status", renderer_status, text=1, foreground=2)
        self.tree_view.append_column(col_status)
        
        scrolled.add(self.tree_view)
        
        # Empty State
        self.empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.empty_box.set_valign(Gtk.Align.CENTER)
        self.empty_box.set_halign(Gtk.Align.CENTER)
        empty_icon = Gtk.Image.new_from_icon_name("network-vpn-symbolic", Gtk.IconSize.DIALOG)
        empty_label = Gtk.Label(label="No VPN clients found. Add one below.")
        empty_label.get_style_context().add_class("muted-text")
        self.empty_box.pack_start(empty_icon, False, False, 0)
        self.empty_box.pack_start(empty_label, False, False, 0)
        
        self.client_stack.add_named(scrolled, "list")
        self.client_stack.add_named(self.empty_box, "empty")
        
        self.clients_box.pack_start(self.client_stack, True, True, 0)
        
        # Client Actions
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        
        self.btn_add = Gtk.Button(label="Add Client")
        self.btn_add.get_style_context().add_class("primary-action")
        self.btn_add.connect("clicked", self.on_add_client_dialog)
        
        self.btn_revoke = Gtk.Button(label="Revoke Selected")
        self.btn_revoke.get_style_context().add_class("destructive-action")
        self.btn_revoke.connect("clicked", self.on_revoke_client)
        
        self.btn_refresh = Gtk.Button(label="Refresh")
        self.btn_refresh.get_style_context().add_class("secondary-action")
        self.btn_refresh.connect("clicked", lambda x: self.refresh_state())
        
        actions_box.pack_start(self.btn_add, False, False, 0)
        actions_box.pack_start(self.btn_revoke, False, False, 0)
        actions_box.pack_end(self.btn_refresh, False, False, 0)
        
        self.clients_box.pack_start(actions_box, False, False, 0)
        self.clients_frame.add(self.clients_box)
        
        self.add(self.clients_frame)
        
        # Initial state is deferred until the Infrastructure tab is first shown
        # (see MainWindow._on_tab_switch). This avoids a global busy flash on launch.

    def log(self, text):
        """Helper para loguear opcionalmente."""
        if self.log_cb:
            self.log_cb(text)
        else:
            logging.info(f"[VPNPanel] {text}")

    def set_busy(self, busy, msg="Processing..."):
        """Route busy state through the main window's reference-counted system."""
        if self.set_busy_cb:
            self.set_busy_cb(busy, msg)

    def run_async(self, func, *args, callback=None):
        self.set_busy(True, "Processing VPN task...")
        
        def task_wrapper():
            try:
                return TaskResult(True, data=func(*args))
            except Exception as e:
                return TaskResult(False, error=str(e))

        future = self.executor.submit(task_wrapper)
        
        def on_done(f):
            self.set_busy(False)
            try:
                res = f.result()
                if res.success:
                    net_res = res.data
                    if callback: GLib.idle_add(callback, net_res)
                    GLib.idle_add(lambda: self.log(net_res.to_log_entry()))
                    
                    # Unified auth cancellation detection (message + details)
                    if not net_res.success:
                        text = (net_res.message + " " + (net_res.details or "")).lower()
                        if any(w in text for w in ("cancel", "dismissed")):
                            GLib.idle_add(lambda: self._show_error(
                                "Authentication Required",
                                "This VPN operation requires administrator privileges."
                            ))
                else:
                    GLib.idle_add(lambda: self.log(f"❌ VPN Error: {res.error}"))
            except Exception as exc:
                err_msg = str(exc)
                GLib.idle_add(lambda: self.log(f"❌ Critical: {err_msg}"))
                
        future.add_done_callback(on_done)

    def _show_error(self, title, message):
        """Shows an error dialog using the main window when available."""
        parent = self.main_window
        if parent is None:
            toplevel = self.get_toplevel()
            parent = toplevel if isinstance(toplevel, Gtk.Window) else None
        if parent is None or getattr(parent, "is_destroyed", False):
            return

        dialog = Gtk.MessageDialog(
            transient_for=parent,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def refresh_state(self):
        def update_ui(status_res):
            if not status_res.success:
                self._needs_retry = True
                self._state_loaded = False
                self.status_label.set_text(f"VPN Error: {status_res.message}")
                return

            self._needs_retry = False
            self._state_loaded = True
            status = status_res.message

            # Update Header
            if status == OperatorStatus.NOT_INSTALLED.value:
                self.status_label.set_text("VPN Not Installed")
                self.action_btn.set_label("Install OpenVPN")
                self.action_btn.get_style_context().add_class("primary-action")
                self.action_btn.set_sensitive(True)
                self.clients_frame.set_sensitive(False) # Disable client list
            
            elif status == OperatorStatus.RUNNING.value:
                self.status_label.set_text("VPN Running")
                self.action_btn.set_label("Re-Check Status")
                self.action_btn.get_style_context().remove_class("primary-action")
                self.action_btn.get_style_context().add_class("secondary-action")
                self.action_btn.set_sensitive(True)
                self.clients_frame.set_sensitive(True)
                # Auto-load clients via privileged IPC (PKI index read).
                self.run_async(
                    lambda: self.actions.call("vpn_list_clients"),
                    callback=self.update_client_list,
                )

            elif status == OperatorStatus.STOPPED.value:
                self.status_label.set_text("VPN Service Stopped")
                self.action_btn.set_label("Start VPN Service")
                self.action_btn.get_style_context().add_class("primary-action")
                self.action_btn.set_sensitive(True)
                self.clients_frame.set_sensitive(True)
                self.run_async(
                    lambda: self.actions.call("vpn_list_clients"),
                    callback=self.update_client_list,
                )

            else: # ERROR / UNKNOWN
                self.status_label.set_text(f"Status: {status}")
                self.clients_frame.set_sensitive(False)

        self.run_async(lambda: self.actions.call("vpn_status"), callback=update_ui)

    def update_client_list(self, result: NetResult):
        self.client_list_store.clear()
        if not result.success or not result.data:
            self.client_stack.set_visible_child_name("empty")
            return

        self.client_stack.set_visible_child_name("list")

        for client in result.data:
            color = "#4CAF50" if client.active else "#9E9E9E"
            status_text = "Active" if client.active else "Revoked"
            self.client_list_store.append([client.name, status_text, color])

    def on_main_action(self, widget):
        label = widget.get_label()
        if "Install" in label:
            dialog = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text="Install OpenVPN Server?",
            )
            dialog.format_secondary_text("This will download and configure OpenVPN using Angristan's script.\nIt requires root privileges and SHA256 integrity verification.")
            response = dialog.run()
            dialog.destroy()
            
            if response == Gtk.ResponseType.OK:
                self.run_async(
                    lambda: self.actions.call("vpn_install"),
                    callback=lambda _: self.refresh_state(),
                )
        elif "Start VPN" in label:
            dialog = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text="Start OpenVPN Service?",
            )
            dialog.format_secondary_text("This requires administrator privileges.")
            response = dialog.run()
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                self.run_async(
                    lambda: self.actions.call("vpn_start_service"),
                    callback=lambda _: self.refresh_state(),
                )
        else:
            self.refresh_state()

    def on_add_client_dialog(self, widget):
        dialog = Gtk.Dialog(title="Add VPN Client", transient_for=self.get_toplevel(), flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        
        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(10)
        
        entry = Gtk.Entry()
        entry.set_placeholder_text("Client Name (e.g. laptop-carlos)")
        box.add(Gtk.Label(label="Enter new client name:"))
        box.add(entry)
        
        dialog.show_all()
        response = dialog.run()
        name = entry.get_text().strip()
        dialog.destroy()
        
        if response == Gtk.ResponseType.OK:
            if not name:
                self._show_error("Invalid Name", "Please enter a client name.")
                return
            self.run_async(
                lambda: self.actions.call("vpn_create_client", {"name": name}),
                callback=lambda _: self.run_async(
                    lambda: self.actions.call("vpn_list_clients"),
                    callback=self.update_client_list,
                ),
            )

    def on_revoke_client(self, widget):
        selection = self.tree_view.get_selection()
        model, treeiter = selection.get_selected()
        if not treeiter:
            self._show_error("No Selection", "Select a client to revoke.")
            return

        name = model[treeiter][0]
        dialog = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Revoke client '{name}'?",
        )
        dialog.format_secondary_text("This action cannot be easily undone. The client certificate will be revoked.")
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            self.run_async(
                lambda: self.actions.call("vpn_revoke_client", {"name": name}),
                callback=lambda _: self.run_async(
                    lambda: self.actions.call("vpn_list_clients"),
                    callback=self.update_client_list,
                ),
            )
