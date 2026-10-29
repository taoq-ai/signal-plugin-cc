"""Whether the owner is at the Mac, from keyboard and mouse idle time."""
import re
import subprocess

RETURNED = 10  # seconds of idle time below which the owner counts as back


def idle_seconds():
    """Seconds since the last keyboard or mouse input on macOS; None elsewhere."""
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"],
                             capture_output=True, text=True).stdout
    except OSError:
        return None
    m = re.search(r'"HIDIdleTime" = (\d+)', out)
    return int(m.group(1)) / 1e9 if m else None


def away(cfg):
    """True when the Mac has been idle for cfg.idle seconds, or idle time is unknown."""
    idle = idle_seconds()
    return idle is None or idle >= cfg.idle


def returned():
    idle = idle_seconds()
    return idle is not None and idle < RETURNED
