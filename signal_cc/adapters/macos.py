"""Presence from the Mac's keyboard and mouse idle time."""
import re
import subprocess

RETURNED = 10  # seconds of idle time below which the owner counts as back


def idle_seconds():
    """Seconds since the last keyboard or mouse input on macOS; None elsewhere."""
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"], capture_output=True, text=True).stdout
    except OSError:
        return None
    m = re.search(r'"HIDIdleTime" = (\d+)', out)
    return int(m.group(1)) / 1e9 if m else None


class MacPresence:
    def __init__(self, idle):
        self.idle = idle  # seconds without input before the Mac counts as unattended

    def away(self):
        """Idle for self.idle seconds, or idle time unknown (not a Mac): prompts go to Signal."""
        idle = idle_seconds()
        return idle is None or idle >= self.idle

    def returned(self):
        idle = idle_seconds()
        return idle is not None and idle < RETURNED
