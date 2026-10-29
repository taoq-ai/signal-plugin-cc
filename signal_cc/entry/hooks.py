"""The Claude Code hook handlers. Each takes the config and the hook's input and returns the hook's output
or None; None lets Claude Code go on as it would without the plugin."""
import os
import re
import sys
import time

from ..adapters import processes
from ..app import desk
from ..app.conversation import continue_session
from ..domain.forms import ContinueForm, PermissionForm, PlanForm, QuestionForm
from ..domain.model import AT_MAC, CLOSED
from . import wiring

WOKEN = "The owner replied from Signal, away from the Mac (signal-plugin-cc):"  # listen()'s wake, seen by quiet()
REPORT = "<task-notification>"  # how Claude Code opens a prompt it submits itself, a background task's report


def project(hook):
    return os.path.basename(hook.get("cwd", "")) or "Claude Code"


class Refused(ValueError):
    """Hook input the relay will not act on."""


def session_id(hook):
    """The session id, a file name under the home, so a plain token only (Claude Code sends a UUID)."""
    session = hook.get("session_id", "unknown")
    if not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", session):
        raise Refused(f"session_id {session!r} is not a plain token, not used")
    return session


def permission(cfg, hook):
    """PermissionRequest: allow or deny a tool call, or approve a plan (ExitPlanMode)."""
    tool, tool_input = hook["tool_name"], hook.get("tool_input", {})
    if tool == "AskUserQuestion":  # question() answers it
        return None
    form = PlanForm(tool_input, project(hook)) if tool == "ExitPlanMode" \
        else PermissionForm(tool, tool_input, project(hook))
    decision = wiring.conversation(cfg, session_id(hook)).ask(form)
    return decision and {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}


def question(cfg, hook):
    """PreToolUse on AskUserQuestion: answer the questions."""
    answers = wiring.conversation(cfg, session_id(hook)).ask(QuestionForm(hook["tool_input"]["questions"], project(hook)))
    return answers and {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "updatedInput": {**hook["tool_input"], "answers": answers}}}


def self_started(prompt):
    """A prompt Claude Code submitted itself (a background task's report, the Signal wake among them), not one
    typed at the Mac."""
    return prompt.lstrip().startswith(REPORT) or WOKEN in prompt


def quiet(cfg, hook):
    """UserPromptSubmit and SessionEnd: stop this session's listener, so a late Signal reply can't wake it.
    A prompt typed at the Mac also turns the away switch off. A turn Claude Code started itself changes nothing:
    the listener keeps waiting for a reply. The listener learns why it stops, so a message still waiting on
    Signal is told the Mac took over or the session closed, and then the session forgets its earlier messages."""
    listeners, session = wiring.listeners(cfg), session_id(hook)
    event = hook.get("hook_event_name")
    if event == "UserPromptSubmit" and self_started(hook.get("prompt") or ""):
        return
    typed = event == "UserPromptSubmit"
    pid = listeners.get(session)
    listeners.clear(session)
    processes.stop(pid, AT_MAC if typed else CLOSED if event == "SessionEnd" else None)
    if typed:
        wiring.presence(cfg).set_switch(False)
    if typed or event == "SessionEnd":  # replies to its earlier messages no longer reach it
        wiring.registry(cfg).forget(session)


def listen(cfg, hook):
    """Stop, in the background with asyncRewake: once the owner is away, send Claude's last message and
    wake the session with the reply by exiting 2 with it on stderr. A headless run (claude -p) waits for
    this hook, and nobody can continue it, so there it returns at once."""
    if processes.headless():
        return None
    quiet(cfg, hook)  # replace the listener of the session's previous turn
    listeners, session = wiring.listeners(cfg), session_id(hook)
    listeners.set(session, os.getpid())
    processes.exit_on_sigterm()  # quieted: let the conversation clean up
    try:
        reply = continue_session(wiring.conversation(cfg, session),
                                 ContinueForm(hook.get("last_assistant_message"), project(hook)),
                                 grace=cfg.wait, wait=cfg.listen)
    finally:
        listeners.clear(session, os.getpid())
    if reply:
        print(f"{WOKEN}\n{reply}", file=sys.stderr)
        sys.exit(2)


def start(cfg, hook):
    """SessionStart: start the signal-cli daemon and the desk unless they are running."""
    daemon = wiring.daemon(cfg)
    if not daemon.is_up():
        daemon.start()
    processes.spawn("desk", cfg.home / "daemon.log")  # a second desk exits at once


def run_desk(cfg, hook=None):
    """The desk process: answer commands while the daemon runs. Only one desk runs on the Mac."""
    lock = wiring.desk_lock(cfg)
    if not lock.acquire():
        return None
    try:
        daemon = wiring.daemon(cfg)
        for _ in range(60):  # SessionStart may have started the daemon a moment ago
            if daemon.is_up():
                break
            time.sleep(1)
        desk.serve(daemon, wiring.registry(cfg), wiring.presence(cfg))
    finally:
        lock.release()
