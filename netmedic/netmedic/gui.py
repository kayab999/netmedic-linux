import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from netmedic.ui import MainWindow


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
    GLib.set_prgname("netmedic")
    GLib.set_application_name("NetMedic")
    win = MainWindow()
    win.show_all()
    Gtk.main()