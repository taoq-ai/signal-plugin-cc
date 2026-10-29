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
    def __init__(self, idle, switch):
        self.idle = idle  # seconds without input before the Mac counts as unattended
        self.switch = switch  # the away switch: on() and set(on)

    def away(self):
        """The switch is on, or the Mac has been idle for self.idle seconds. Unknown idle time (not a Mac)
        counts as at the computer."""
        if self.switch.on():
            return True
        idle = idle_seconds()
        return idle is not None and idle >= self.idle

    def returned(self):
        """Input in the last few seconds, unless the switch is on."""
        if self.switch.on():
            return False
        idle = idle_seconds()
        return idle is not None and idle < RETURNED

    def set_switch(self, on):
        self.switch.set(on)

    def switch_on(self):
        return self.switch.on()
