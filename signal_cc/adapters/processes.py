"""The relay's own background processes."""
import os
import signal
import subprocess
import sys
from pathlib import Path

from ..domain.model import AT_MAC, CLOSED, Stopped
from . import private

RELAY = Path(__file__).resolve().parents[2] / "relay.py"
SIGNALS = {None: signal.SIGTERM, AT_MAC: signal.SIGUSR1, CLOSED: signal.SIGUSR2}  # why a listener stops


def is_relay(pid):
    """True when pid is a live relay.py process, never another process that reused the pid."""
    cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    return pid != os.getpid() and "relay.py" in cmd


def headless():
    """True in a print-mode run (claude -p), which waits for its Stop hook to end. Claude Code's own
    arguments decide: CLAUDE_CODE_ENTRYPOINT is sdk-cli there, but a claude -p started from another
    session inherits that session's value. Print mode with streaming input (an SDK host) is not headless."""
    pid, cmd = os.environ.get("CLAUDE_PID", ""), ""
    if pid.isdigit():  # one process: ps reads a list such as 1,2 as several
        try:
            cmd = subprocess.run(["ps", "-o", "command=", "-p", pid], capture_output=True, text=True).stdout
        except OSError:  # no ps
            pass
    if not cmd:
        return os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "sdk-cli"
    args = cmd.split()
    streaming = "--input-format=stream-json" in args or any(
        a == "--input-format" and b == "stream-json" for a, b in zip(args, args[1:]))
    return bool({"-p", "--print"} & set(args)) and not streaming


def stop(pid, why=None):
    """Stop a relay process, telling it why (see exit_on_sigterm)."""
    if pid and is_relay(pid):
        os.kill(pid, SIGNALS[why])


def spawn(command, log):
    """Run relay.py <command> in the background, detached from the hook that starts it."""
    private.home(log.parent)
    with private.open_file(log, "ab") as out:
        subprocess.Popen([sys.executable, str(RELAY), command], stdin=subprocess.DEVNULL, stdout=out,
                         stderr=out, start_new_session=True)


def exit_on_sigterm():
    """Turn the signals stop sends into Stopped (a SystemExit with status 0) carrying why, so finally
    blocks (releasing a prompt, closing polls) run."""
    for why, sig in SIGNALS.items():
        signal.signal(sig, lambda *_, why=why: _raise(Stopped(why)))


def _raise(error):
    raise error
