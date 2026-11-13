"""Where the unit tests find what they test and what they share.

The tests lie outside the plugin's folder, which an install copies whole. The proof of the core
without its add-ons copies plugin and tests into a temporary folder in this same position to each
other, so these paths hold there too.
"""

from __future__ import annotations

from pathlib import Path

_CHECKOUT = Path(__file__).resolve().parents[2]

PLUGIN_ROOT = _CHECKOUT / "plugins" / "m2b"
# The scripted stand-ins for the commands the core starts: claude, reminders and osascript.
FAKES = Path(__file__).resolve().parent / "fakes"
