"""The relay's own background processes."""
import os
import signal
import subprocess
import sys
from pathlib import Path

from ..domain.model import AT_MAC, CLOSED, Stopped

RELAY = Path(__file__).resolve().parents[2] / "relay.py"
SIGNALS = {None: signal.SIGTERM, AT_MAC: signal.SIGUSR1, CLOSED: signal.SIGUSR2}  # why a listener stops


def is_relay(pid):
    """True when pid is a live relay.py process, never another process that reused the pid."""
    cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    return pid != os.getpid() and "relay.py" in cmd


def stop(pid, why=None):
    """Stop a relay process, telling it why (see exit_on_sigterm)."""
    if pid and is_relay(pid):
        os.kill(pid, SIGNALS[why])


def spawn(command, log):
    """Run relay.py <command> in the background, detached from the hook that starts it."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as out:
        subprocess.Popen([sys.executable, str(RELAY), command], stdin=subprocess.DEVNULL, stdout=out,
                         stderr=out, start_new_session=True)


def exit_on_sigterm():
    """Turn the signals stop sends into Stopped (a SystemExit with status 0) carrying why, so finally
    blocks (releasing a prompt, closing polls) run."""
    for why, sig in SIGNALS.items():
        signal.signal(sig, lambda *_, why=why: _raise(Stopped(why)))


def _raise(error):
    raise error
