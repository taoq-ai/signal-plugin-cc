"""Send one prompt over Signal and wait for the owner's answer.

Several sessions can wait at once, and a reply never reaches the wrong one. A reply counts for a prompt
only when it quotes one of the prompt's messages, starts with its tag, or is a plain reply while the
prompt is the only one waiting and the latest message the relay sent belongs to it. For any other plain
reply, the oldest waiting prompt sends one hint that lists the waiting prompts.
"""
import json
import queue
import re
import secrets
import time

from . import presence
from .daemon import Daemon

TAGGED = re.compile(r"\[?([0-9a-f]{4})\]?(?:\s+|$)(.*)", re.I | re.S)


def waiting(cfg):
    """The prompts still waiting, as (created, tag, summary), oldest first."""
    now = time.time()
    live = []
    for p in cfg.pending.iterdir():
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if d["deadline"] > now:
            live.append((d["created"], p.name, d["summary"]))
    return sorted(live)


def register(cfg, summary):
    """Claim a tag no waiting prompt holds. The claim exists before the prompt is sent, so no
    other session can take a plain reply to it as its own."""
    cfg.pending.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for p in cfg.pending.iterdir():  # drop the claims of prompts that ended without cleaning up
        try:
            if json.loads(p.read_text())["deadline"] < now:
                p.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError):
            pass
    while True:
        tag = secrets.token_hex(2)
        try:
            with open(cfg.pending / tag, "x") as f:
                json.dump({"created": now, "deadline": now + cfg.wait, "summary": summary}, f)
            return tag
        except FileExistsError:
            continue


def latest(cfg):
    """The tag of the prompt the relay's latest message belongs to; empty for none."""
    try:
        return (cfg.home / "last").read_text()
    except OSError:
        return ""


def hint(daemon, live):
    lines = "\n".join(f"[{t}] {s}" for _, t, s in live)
    text = f"Which prompt? {len(live)} waiting:\n{lines}\nQuote one, or start your reply with its tag."
    # with one prompt waiting, a plain reply to this hint is for it
    daemon.send(text, tag=live[0][1] if len(live) == 1 else "")


def ask(cfg, text, parse):
    """Send text and return parse(reply) for the first reply addressed to it, or None.

    None when the owner is at the Mac, on timeout, or when they come back to the Mac.
    parse returns None for a reply it can't read; the owner is then asked again.
    """
    if not presence.away(cfg):
        return None
    daemon = Daemon(cfg)
    replies, close = daemon.subscribe()  # before sending, so no reply is missed
    tag = register(cfg, text.splitlines()[0])
    try:
        sent = {daemon.send(f"[{tag}] {text}", tag=tag)}  # timestamps a quoting reply refers to
        deadline = time.time() + cfg.wait
        while time.time() < deadline:
            try:
                reply, quoted = replies.get(timeout=2)
            except queue.Empty:
                if presence.returned():
                    daemon.send(f"[{tag}] You're back at the Mac; answer there.", tag=tag)
                    return None
                continue
            live = waiting(cfg)
            tagged = TAGGED.match(reply)
            if tagged and tagged.group(1).lower() in {t for _, t, _ in live}:
                if tagged.group(1).lower() != tag:
                    continue
                reply = tagged.group(2)
            elif quoted is not None:
                if quoted not in sent:
                    continue
            elif any(t != tag for _, t, _ in live) or latest(cfg) != tag:
                if live and live[0][1] == tag:  # only the oldest answers, so the hint comes once
                    hint(daemon, live)
                continue
            value = parse(reply.strip())
            if value is None:
                sent.add(daemon.send(f"[{tag}] Couldn't read that; try again.", tag=tag))
                continue
            return value
        daemon.send(f"[{tag}] Timed out; answer on the Mac.", tag=tag)
        return None
    finally:
        (cfg.pending / tag).unlink(missing_ok=True)
        close()
