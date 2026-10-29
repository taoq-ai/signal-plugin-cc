"""The Claude Code hook handlers. Each takes the config and the hook's input and returns the hook's output
or None; None lets Claude Code go on as it would without the plugin."""
import os
import sys
import time

from ..adapters import processes
from ..app import desk
from ..app.conversation import continue_session
from ..domain.forms import ContinueForm, PermissionForm, QuestionForm
from . import wiring

NOT_RELAYED = ("AskUserQuestion", "ExitPlanMode")  # question() answers the one; plan approval stays on the Mac


def project(hook):
    return os.path.basename(hook.get("cwd", "")) or "Claude Code"


def permission(cfg, hook):
    """PermissionRequest: allow or deny a tool call."""
    if hook["tool_name"] in NOT_RELAYED:
        return None
    form = PermissionForm(hook["tool_name"], hook.get("tool_input", {}), project(hook))
    decision = wiring.conversation(cfg).ask(form)
    return decision and {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}


def question(cfg, hook):
    """PreToolUse on AskUserQuestion: answer the questions."""
    answers = wiring.conversation(cfg).ask(QuestionForm(hook["tool_input"]["questions"], project(hook)))
    return answers and {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "updatedInput": {**hook["tool_input"], "answers": answers}}}


def quiet(cfg, hook):
    """UserPromptSubmit and SessionEnd: stop this session's listener, so a late Signal reply can't wake it.
    A prompt typed at the Mac also turns the away switch off."""
    if hook.get("hook_event_name") == "UserPromptSubmit":
        wiring.presence(cfg).set_switch(False)
    listeners, session = wiring.listeners(cfg), hook.get("session_id", "unknown")
    pid = listeners.get(session)
    listeners.clear(session)
    processes.stop(pid)


def listen(cfg, hook):
    """Stop, in the background with asyncRewake: once the owner is away, send Claude's last message and
    wake the session with the reply by exiting 2 with it on stderr."""
    quiet(cfg, hook)  # replace the listener of the session's previous turn
    listeners, session = wiring.listeners(cfg), hook.get("session_id", "unknown")
    listeners.set(session, os.getpid())
    processes.exit_on_sigterm()  # quieted: let the conversation clean up
    try:
        reply = continue_session(wiring.conversation(cfg),
                                 ContinueForm(hook.get("last_assistant_message"), project(hook)),
                                 grace=cfg.wait, wait=cfg.listen)
    finally:
        listeners.clear(session, os.getpid())
    if reply:
        print(f"The owner replied from Signal, away from the Mac (signal-plugin-cc):\n{reply}", file=sys.stderr)
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
