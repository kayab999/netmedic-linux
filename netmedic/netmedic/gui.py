import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from netmedic.ui import MainWindow
from netmedic.teardown import register as register_teardown

_main_window = None


def show_error_dialog(message: str):
    """Muestra un diálogo de error GTK simple."""
    dialog = Gtk.MessageDialog(
        transient_for=None,
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text="Error de Instancia",
    )
    dialog.format_secondary_text(message)
    dialog.run()
    dialog.destroy()


def run_gui():
    global _main_window
    GLib.set_prgname("netmedic")
    GLib.set_application_name("NetMedic")
    _main_window = MainWindow()
    register_teardown(_emergency_gui_shutdown)
    _main_window.show_all()
    Gtk.main()


def _emergency_gui_shutdown():
    if _main_window is not None and not getattr(_main_window, "is_destroyed", False):
        _main_window.emergency_shutdown()