#!/usr/bin/env python3
"""Relay Claude Code prompts to Signal and read the answer back.

Hook usage: relay.py start|permission|question|notify, with the hook's JSON on stdin.
It prints a hook decision or nothing; nothing means Claude Code shows its own prompt.
"""
import http.client
import json
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("SIGNAL_CC_HOME", Path.home() / ".config" / "signal-plugin-cc"))
DEFAULTS = {"port": 8299, "wait": 300, "idle": 60, "signal_cli": "signal-cli"}
YES = {"y", "yes", "ok", "allow"}
NO = {"n", "no", "deny"}


def load_config():
    try:
        cfg = {**DEFAULTS, **json.loads((HOME / "config.json").read_text())}
    except (OSError, ValueError):
        return None
    return cfg if cfg.get("bot") and cfg.get("owner") else None


def url(cfg, path):
    return f"http://127.0.0.1:{cfg['port']}/api/v1/{path}"


def send(cfg, text):
    """Send text to the owner and return the message timestamp Signal quotes in replies."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "send",
                       "params": {"recipient": [cfg["owner"]], "message": text}}).encode()
    req = urllib.request.Request(url(cfg, "rpc"), body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["result"]["timestamp"]


def idle_seconds():
    """Seconds since the last keyboard or mouse input on macOS; None elsewhere."""
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem", "-d", "4"],
                             capture_output=True, text=True).stdout
    except OSError:
        return None
    m = re.search(r'"HIDIdleTime" = (\d+)', out)
    return int(m.group(1)) / 1e9 if m else None


def read_events(cfg, resp, out):
    """Put (text, quoted timestamp) on out for each message the owner sends the bot."""
    for line in resp:
        if not line.startswith(b"data:"):
            continue
        event = json.loads(line[5:])
        env = event.get("params", event).get("envelope", {})
        msg = env.get("dataMessage") or {}
        if env.get("sourceNumber", env.get("source")) == cfg["owner"] and msg.get("message"):
            out.put((msg["message"].strip(), (msg.get("quote") or {}).get("id")))


def alone(pending, tag):
    """True when no other prompt is waiting, so an unquoted reply must be for this one."""
    now = time.time()
    for p in pending.iterdir():
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
    """
    idle = idle_seconds()
    if idle is not None and idle < cfg["idle"]:
        return None
    tag = secrets.token_hex(2)
    pending = HOME / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + cfg["wait"]
    conn = http.client.HTTPConnection("127.0.0.1", cfg["port"], timeout=10)
    try:
        conn.connect()
        sock = conn.sock  # getresponse may drop conn.sock on a close-delimited stream
        conn.request("GET", "/api/v1/events")  # subscribe before sending so no reply is missed
        resp = conn.getresponse()
        sock.settimeout(None)
        replies = queue.Queue()
        threading.Thread(target=read_events, args=(cfg, resp, replies), daemon=True).start()
        ts = send(cfg, f"[{tag}] {text}")
        (pending / tag).write_text(str(deadline))
        while time.time() < deadline:
            try:
                reply, quoted = replies.get(timeout=2)
            except queue.Empty:
                idle = idle_seconds()
                if idle is not None and idle < 10:
                    send(cfg, f"[{tag}] You're back at the Mac; answer there.")
                    return None
                continue
            tagged = re.match(rf"\[?{tag}\]?\s*(.*)", reply, re.I | re.S)
            if tagged:
                reply = tagged.group(1)
            elif quoted != ts and not alone(pending, tag):
                continue
            value = parse(reply.strip())
            if value is None:
                send(cfg, f"[{tag}] Couldn't read that; try again.")
                continue
            return value
        send(cfg, f"[{tag}] Timed out; answer on the Mac.")
        return None
    finally:
        (pending / tag).unlink(missing_ok=True)
        conn.close()


def project(hook):
    return os.path.basename(hook.get("cwd", "")) or "Claude Code"


def decide(reply):
    word = reply.lower()
    if word in YES:
        return {"behavior": "allow"}
    reason = "" if word in NO else f": {reply}"
    return {"behavior": "deny", "message": f"Denied from Signal{reason}"}


def permission(cfg, hook):
    tool, inp = hook["tool_name"], hook.get("tool_input", {})
    if tool in ("AskUserQuestion", "ExitPlanMode"):
        return None  # the question hook answers AskUserQuestion; plan approval stays on the Mac
    detail = inp.get("command") or inp.get("file_path") or inp.get("url") or json.dumps(inp)
    what = f"{inp['description']}\n" if inp.get("description") else ""
    text = f"{tool} in {project(hook)}:\n{what}{detail[:600]}\n\nReply y to allow, n or a reason to deny."
    decision = ask(cfg, text, decide)
    return decision and {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                                "decision": decision}}


def pick(q, row):
    """An option number (several for multi-select) becomes its label; anything else is a free answer."""
    nums = [n.strip() for n in row.split(",")]
    if all(n.isdigit() and 1 <= int(n) <= len(q["options"]) for n in nums) \
            and (q.get("multiSelect") or len(nums) == 1):
        return ", ".join(q["options"][int(n) - 1]["label"] for n in nums)
    return row


def question(cfg, hook):
    qs = hook["tool_input"]["questions"]
    lines = [f"Question from {project(hook)}:"]
    for i, q in enumerate(qs, 1):
        lines.append(f"\n{i}. {q['question']}" + (" (several: 1,3)" if q.get("multiSelect") else ""))
        lines += [f"  {j}) {o['label']}" + (f" - {o['description']}" if o.get("description") else "")
                  for j, o in enumerate(q["options"], 1)]
    lines.append("\nReply one line per question: an option number, or your own answer.")

    def parse(reply):
        rows = [reply] if len(qs) == 1 else [r.strip() for r in reply.splitlines() if r.strip()]
        if len(rows) != len(qs):
            return None
        return {q["question"]: pick(q, row) for q, row in zip(qs, rows)}

    answers = ask(cfg, "\n".join(lines), parse)
    return answers and {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "updatedInput": {**hook["tool_input"], "answers": answers}}}


def notify(cfg, hook):
    idle = idle_seconds()
    if idle is None or idle >= cfg["idle"]:
        send(cfg, f"{project(hook)}: {hook.get('message', 'Claude is waiting for you')}")


def start(cfg, hook):
    """Start the signal-cli HTTP daemon unless one is already up."""
    try:
        urllib.request.urlopen(url(cfg, "check"), timeout=2).close()
        return
    except OSError:
        pass
    HOME.mkdir(parents=True, exist_ok=True)
    with open(HOME / "daemon.log", "ab") as log:
        subprocess.Popen([cfg["signal_cli"], "-a", cfg["bot"], "daemon", "--http", f"127.0.0.1:{cfg['port']}"],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)


HANDLERS = {"start": start, "permission": permission, "question": question, "notify": notify}


def main():
    cfg = load_config()
    if not cfg:
        return  # not set up: stay out of the way
    try:
        out = HANDLERS[sys.argv[1]](cfg, json.load(sys.stdin))
    except Exception:
        traceback.print_exc()  # a relay failure must never block the session
        return
    if out:
        print(json.dumps(out))


if __name__ == "__main__":
    main()
