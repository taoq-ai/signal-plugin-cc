"""Send one prompt over Signal and wait for the owner's answer."""
import queue
import re
import secrets
import time

from . import presence
from .daemon import Daemon


def alone(cfg, tag):
    """True when no other prompt is waiting, so an unquoted reply must be for this one."""
    now = time.time()
    for p in cfg.pending.iterdir():
        try:
            if p.name != tag and float(p.read_text()) > now:
                return False
        except (OSError, ValueError):
            pass
    return True


def ask(cfg, text, parse):
    """Send text and return parse(reply) for the first reply it accepts, or None.

    None when the owner is at the Mac, on timeout, or when they come back to the Mac.
    A reply counts when it quotes the prompt, starts with its tag, or is the only prompt waiting.
    parse returns None for a reply it can't read; the owner is then asked again.
    """
    if not presence.away(cfg):
        return None
    daemon = Daemon(cfg)
    tag = secrets.token_hex(2)
    cfg.pending.mkdir(parents=True, exist_ok=True)
    mine = cfg.pending / tag
    deadline = time.time() + cfg.wait
    replies, close = daemon.subscribe()  # before sending, so no reply is missed
    try:
        ts = daemon.send(f"[{tag}] {text}")
        mine.write_text(str(deadline))
        while time.time() < deadline:
            try:
                reply, quoted = replies.get(timeout=2)
            except queue.Empty:
                if presence.returned():
                    daemon.send(f"[{tag}] You're back at the Mac; answer there.")
                    return None
                continue
            tagged = re.match(rf"\[?{tag}\]?\s*(.*)", reply, re.I | re.S)
            if tagged:
                reply = tagged.group(1)
            elif quoted != ts and not alone(cfg, tag):
                continue
            value = parse(reply.strip())
            if value is None:
                daemon.send(f"[{tag}] Couldn't read that; try again.")
                continue
            return value
        daemon.send(f"[{tag}] Timed out; answer on the Mac.")
        return None
    finally:
        mine.unlink(missing_ok=True)
        close()
