"""The Claude Code hook handlers. Each takes the config and the hook's input and returns the hook's output
or None; None lets Claude Code go on as it would without the plugin."""
import os
import sys
import time

from ..adapters import processes
from ..app import desk
from ..app.conversation import continue_session
from ..domain.forms import ContinueForm, PermissionForm, PlanForm, QuestionForm
from . import wiring

WOKEN = "The owner replied from Signal, away from the Mac (signal-plugin-cc):"  # listen()'s wake, seen by quiet()


def project(hook):
    return os.path.basename(hook.get("cwd", "")) or "Claude Code"


def session_id(hook):
    return hook.get("session_id", "unknown")


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


def quiet(cfg, hook):
    """UserPromptSubmit and SessionEnd: stop this session's listener, so a late Signal reply can't wake it.
    A prompt typed at the Mac also turns the away switch off; a turn woken from Signal does not."""
    listeners, session = wiring.listeners(cfg), session_id(hook)
    pid = listeners.get(session)
    listeners.clear(session)
    processes.stop(pid)
    if hook.get("hook_event_name") == "UserPromptSubmit" and WOKEN not in hook.get("prompt", ""):
        wiring.presence(cfg).set_switch(False)


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
