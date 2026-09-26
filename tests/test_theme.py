"""Theme guardians: the app owns its appearance independent of ambient theme.

Unstyled container surfaces (Gtk.Frame etc.) followed the system gtk-theme
while the rest of the window is dark — white frames on dock launch. These
tests pin the fix: explicit container selectors + dark-variant preference.
"""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402
from unittest.mock import patch  # noqa: E402

from netmedic.theme import CSS, apply_theme  # noqa: E402

REQUIRED_SELECTORS = (
    "frame {",
    "frame > border",
    "headerbar {",
    "separator {",
    "scrollbar slider",
    "viewport {",
    "treeview",
    "tooltip {",
    "notebook stack",
    "stack {",
    "textview.log-view text {",
)


def test_css_parses_without_errors():
    errors = []
    provider = Gtk.CssProvider()
    provider.connect("parsing-error", lambda *args: errors.append(args))
    provider.load_from_data(CSS.encode("utf-8"))
    assert errors == []


def test_container_selectors_present():
    for selector in REQUIRED_SELECTORS:
        assert selector in CSS, f"missing container selector: {selector}"


def test_prefer_dark_requested():
    with patch("netmedic.theme.Gtk.Settings") as mock_settings:
        instance = mock_settings.get_default.return_value
        with patch("netmedic.theme.Gdk.Screen.get_default", return_value=None):
            apply_theme()  # must not raise; provider skipped without screen
        instance.set_property.assert_called_once_with(
            "gtk-application-prefer-dark-theme", True
        )


def test_apply_theme_survives_gtk_failures():
    with patch(
        "netmedic.theme.Gtk.Settings.get_default", side_effect=RuntimeError("no settings")
    ):
        apply_theme()  # guarded, must not raise
