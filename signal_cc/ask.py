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


PARTIAL = object()  # parse took the reply, but answers are still missing
SETTLE = 5  # seconds to let taps on a multi-select poll settle before answering


def ask(cfg, text, parse, polls=(), confirm=None, wait=None, leave_on_return=True):
    """Send text, then one poll per (question, options, multi) in polls; return the value parse builds.

    parse(reply, target) gets each Reply addressed to this prompt, with target the index of the poll it
    votes in or quotes, or None for the text message, its tag or a plain reply. It returns the final
    value, PARTIAL while answers are missing, or None for a reply it can't read (the owner is asked
    again). confirm(value), if given, is sent back as a short receipt; it also clears the spinner the
    phone shows on a vote. wait overrides cfg.wait. None when the owner is at the Mac, on timeout, or
    (with leave_on_return) when they come back to the Mac.
    """
    if not presence.away(cfg):
        return None
    daemon = Daemon(cfg)
    replies, close = daemon.subscribe()  # before sending, so no reply is missed
    tag = register(cfg, text.splitlines()[0])
    sent = {}  # timestamp of each message of this prompt -> the poll index it holds, or None
    try:
        sent[daemon.send(f"[{tag}] {text}", tag=tag)] = None
        for i, (question, options, multi) in enumerate(polls):
            try:
                sent[daemon.send_poll(f"[{tag}] {question}"[:200], options, multi, tag=tag)] = i
            except RuntimeError:
                break  # the text message still takes replies
        value, settle = None, 0
        deadline = time.time() + (wait or cfg.wait)
        while time.time() < deadline:
            if value is not None and time.time() >= settle:
                break
            try:
                reply = replies.get(timeout=2 if value is None else max(0.1, settle - time.time()))
            except queue.Empty:
                if value is None and leave_on_return and presence.returned():
                    daemon.send(f"[{tag}] You're back at the Mac; answer there.", tag=tag)
                    return None
                continue
            live = waiting(cfg)
            tagged = TAGGED.match(reply.text)
            target = None
            if tagged and tagged.group(1).lower() in {t for _, t, _ in live}:
                if tagged.group(1).lower() != tag:
                    continue
                reply = reply._replace(text=tagged.group(2).strip())
            elif reply.quoted is not None:
                if reply.quoted not in sent:
                    continue
                target = sent[reply.quoted]
            elif any(t != tag for _, t, _ in live) or latest(cfg) != tag:
                if live and live[0][1] == tag:  # only the oldest answers, so the hint comes once
                    hint(daemon, live)
                continue
            result = parse(reply, target)
            if result is None:
                sent[daemon.send(f"[{tag}] Couldn't read that; try again.", tag=tag)] = None
            elif result is not PARTIAL:
                value = result
                if reply.votes is not None and polls[target][2]:
                    settle = max(settle, time.time() + SETTLE)
        if value is None:
            daemon.send(f"[{tag}] Timed out; answer on the Mac.", tag=tag)
        elif confirm:
            daemon.send(f"[{tag}] \N{CHECK MARK} {confirm(value)}", tag=None)  # the prompt is done
        return value
    finally:
        (cfg.pending / tag).unlink(missing_ok=True)
        for ts, poll in sent.items():
            if poll is not None:
                try:
                    daemon.end_poll(ts)
                except (OSError, RuntimeError):
                    pass
        close()
