import gi
import logging
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from netmedic.operators.vpn.angristan import AngristanOperator
from netmedic.operators.base import OperatorStatus
from netmedic.models import NetResult, TaskResult

class VPNPanel(Gtk.Box):
    def __init__(self, executor, log_callback=None, set_busy_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_border_width(10)
        
        self.executor = executor
        self.log_cb = log_callback
        self.set_busy_cb = set_busy_callback
        self.operator = AngristanOperator()
        
        # --- UI Components ---
        
        # 1. Header (Status & Main Action)
        self.header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.status_label = Gtk.Label(label="VPN Status: Checking...")
        self.status_label.get_style_context().add_class("header-text")
        
        self.action_btn = Gtk.Button(label="Action")
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
        renderer_text = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn("Name", renderer_text, text=0)
        self.tree_view.append_column(col_name)
        
        # Col 2: Status
        col_status = Gtk.TreeViewColumn("Status", renderer_text, text=1, foreground=2)
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
        
        # Initial State
        self.refresh_state()

    def log(self, text):
        """Helper para loguear opcionalmente."""
        if self.log_cb:
            self.log_cb(text)
        else:
            logging.info(f"[VPNPanel] {text}")

    def set_busy(self, busy, msg="Processing..."):
        """Helper para mostrar estado ocupado opcionalmente."""
        if self.set_busy_cb:
            self.set_busy_cb(busy, msg)

    def run_async(self, func, *args, callback=None):
        self.set_busy(True, "Processing VPN task...")
        self.set_sensitive(False) # Lock UI
        
        def task_wrapper():
            try:
                return TaskResult(True, data=func(*args))
            except Exception as e:
                return TaskResult(False, error=str(e))

        future = self.executor.submit(task_wrapper)
        
        def on_done(f):
            GLib.idle_add(lambda: self.set_busy(False))
            GLib.idle_add(lambda: self.set_sensitive(True)) # Unlock UI
            try:
                res = f.result()
                if res.success:
                    net_res = res.data
                    if callback: GLib.idle_add(callback, net_res)
                    GLib.idle_add(lambda: self.log(net_res.to_log_entry()))
                    
                    # Feedback para elevación cancelada
                    if not net_res.success and "cancelada" in net_res.message.lower():
                        GLib.idle_add(lambda: self._show_error(
                            "Autenticación Requerida", 
                            "La operación VPN requiere privilegios de administrador."
                        ))
                else:
                    GLib.idle_add(lambda: self.log(f"❌ VPN Error: {res.error}"))
            except Exception as e:
                GLib.idle_add(lambda: self.log(f"❌ Critical: {e}"))
                
        future.add_done_callback(on_done)

    def _show_error(self, title, message):
        """Muestra un diálogo de error si el panel está en una ventana."""
        toplevel = self.get_toplevel()
        if not toplevel or not isinstance(toplevel, Gtk.Window): return
        
        dialog = Gtk.MessageDialog(
            transient_for=toplevel,
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
                self.clients_frame.set_sensitive(True)
                # Auto-load clients
                self.run_async(self.operator.list_clients, callback=self.update_client_list)
            
            elif status == OperatorStatus.STOPPED.value:
                self.status_label.set_text("VPN Service Stopped")
                self.action_btn.set_label("Start Service (Not Impl)")
                self.clients_frame.set_sensitive(True) # Can still see list
                self.run_async(self.operator.list_clients, callback=self.update_client_list)
                
            else: # ERROR / UNKNOWN
                self.status_label.set_text(f"Status: {status}")
                self.clients_frame.set_sensitive(False)

        self.run_async(self.operator.check_status, callback=update_ui)

    def update_client_list(self, result: NetResult):
        self.client_list_store.clear()
        if not result.success or not result.data:
            self.client_stack.set_visible_child_name("empty")
            return

        self.client_stack.set_visible_child_name("list")

        for client in result.data:
            color = "green" if client.active else "gray"
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
            dialog.format_secondary_text("This will download and configure OpenVPN using Angristan's script.\nIt requiere Root y verificación de integridad SHA256.")
            response = dialog.run()
            dialog.destroy()
            
            if response == Gtk.ResponseType.OK:
                self.run_async(self.operator.install, callback=lambda _: self.refresh_state())
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
        
        if response == Gtk.ResponseType.OK and name:
            self.run_async(self.operator.add_client, name, callback=lambda _: self.run_async(self.operator.list_clients, callback=self.update_client_list))

    def on_revoke_client(self, widget):
        selection = self.tree_view.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter:
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
                 self.run_async(self.operator.revoke_client, name, callback=lambda _: self.run_async(self.operator.list_clients, callback=self.update_client_list))
