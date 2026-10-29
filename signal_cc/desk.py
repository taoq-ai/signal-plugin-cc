"""The desk: one background process per Mac that answers commands sent from Signal.

`status` lists what is waiting for the owner. Prompts and listeners ignore a plain command, so it is
never taken as an answer. The desk runs while the signal-cli daemon does; SessionStart starts it.
"""
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

from .ask import command, waiting
from .daemon import Daemon

RELAY = Path(__file__).resolve().parent.parent / "relay.py"


def is_relay(pid):
    """True when pid is a live relay.py process, never another process that reused the pid."""
    cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    return pid != os.getpid() and "relay.py" in cmd


def status(cfg):
    live = waiting(cfg) if cfg.pending.exists() else []
    if not live:
        return "Nothing is waiting for you.", ""
    now = time.time()
    lines = [f"[{tag}] {summary} \N{MIDDLE DOT} {round((now - created) / 60)} min ago"
             for created, tag, summary in live]
    text = f"Waiting for you ({len(live)}):\n" + "\n".join(lines)
    if len(live) > 1:
        text += "\nQuote one, or start your reply with its tag."
    # with one prompt waiting, a plain reply to the status is for it
    return text, live[0][1] if len(live) == 1 else ""


def spawn(cfg):
    """Start the desk in the background; a second desk exits at once (see run)."""
    with open(cfg.home / "daemon.log", "ab") as log:
        subprocess.Popen([sys.executable, str(RELAY), "desk"], stdin=subprocess.DEVNULL, stdout=log,
                         stderr=log, start_new_session=True)


def run(cfg, hook=None):
    """Answer commands until the daemon's event stream ends. Only one desk runs: it holds a lock."""
    lock = open(cfg.home / "desk.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return
    daemon = Daemon(cfg)
    for _ in range(60):  # SessionStart may have started the daemon a moment ago
        if daemon.is_up():
            break
        time.sleep(1)
    replies, close = daemon.subscribe()
    try:
        while (reply := replies.get()) is not None:
            if command(reply) == "status":
                text, tag = status(cfg)
                daemon.send(text, tag=tag)
    finally:
        close()
        lock.close()
