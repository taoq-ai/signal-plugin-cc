"""The relay's own background processes."""
import os
import signal
import subprocess
import sys
from pathlib import Path

RELAY = Path(__file__).resolve().parents[2] / "relay.py"


def is_relay(pid):
    """True when pid is a live relay.py process, never another process that reused the pid."""
    cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    return pid != os.getpid() and "relay.py" in cmd


def stop(pid):
    if pid and is_relay(pid):
        os.kill(pid, signal.SIGTERM)


def spawn(command, log):
    """Run relay.py <command> in the background, detached from the hook that starts it."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as out:
        subprocess.Popen([sys.executable, str(RELAY), command], stdin=subprocess.DEVNULL, stdout=out,
                         stderr=out, start_new_session=True)


def exit_on_sigterm():
    """Turn SIGTERM into SystemExit, so finally blocks (releasing a prompt, closing polls) run."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
