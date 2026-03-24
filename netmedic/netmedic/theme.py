import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

CSS = """
/* The background */
window {
    background-color: #121212;
    color: #E0E0E0;
}

/* Notebook styling */
notebook {
    background-color: #121212;
}
notebook header {
    background-color: #1A1A1A;
}
notebook header tab {
    padding: 8px 16px;
    background-color: #1A1A1A;
    color: #A0A0A0;
    border: none;
    box-shadow: none;
}
notebook header tab:checked {
    background-color: #252525;
    color: #FFFFFF;
    border-bottom: 2px solid #4A90E2;
}

/* Cards / Surfaces */
.surface-card {
    background-color: #1E1E1E;
    border-radius: 8px;
    border: 1px solid #333333;
    padding: 12px;
}

/* Buttons */
button {
    background-color: #2A2A2A;
    color: #E0E0E0;
    border: 1px solid #444444;
    border-radius: 6px;
    padding: 8px 16px;
    box-shadow: none;
    text-shadow: none;
    background-image: none;
}
button:hover {
    background-color: #383838;
}
button:active {
    background-color: #202020;
}
button:disabled {
    background-color: #1A1A1A;
    color: #555555;
    border: 1px solid #333333;
}

/* Primary Button */
button.primary-action {
    background-color: #2D63B5;
    color: #FFFFFF;
    border: 1px solid #1E4685;
}
button.primary-action:hover {
    background-color: #3875D1;
}

/* Destructive Button */
button.destructive-action {
    background-color: #8C2A2A;
    color: #FFFFFF;
    border: 1px solid #6B1D1D;
}
button.destructive-action:hover {
    background-color: #A83232;
}

/* Secondary Button */
button.secondary-action {
    background-color: transparent;
    border: 1px solid #555555;
}

/* Log TextView */
textview.log-view {
    background-color: #121212;
    color: #A89984;
}
textview.log-view text selection {
    background-color: #3C3836;
    color: #EBDBB2;
}

/* Typography */
label.warning-text {
    color: #D79921;
}
label.muted-text {
    color: #666666;
}
label.header-text {
    font-weight: bold;
    font-size: 1.1em;
    color: #FFFFFF;
}
"""

def apply_theme():
    screen = Gdk.Screen.get_default()
    if screen:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
