"""The hook handlers: each takes the config and the hook's input and returns its output or None."""
import json
import os
import re
import sys
import traceback

from . import presence
from .ask import PARTIAL, ask
from .config import Config
from .daemon import Daemon

YES = {"y", "yes", "ok", "allow", "\N{THUMBS UP SIGN}"}
NO = {"n", "no", "deny", "\N{THUMBS DOWN SIGN}"}


def project(hook):
    return os.path.basename(hook.get("cwd", "")) or "Claude Code"


def decide(reply):
    word = re.sub("[\U0001F3FB-\U0001F3FF️]", "", reply).lower()  # 👍🏽 counts as 👍
    if word in YES:
        return {"behavior": "allow"}
    reason = "" if word in NO else f": {reply}"
    return {"behavior": "deny", "message": f"Denied from Signal{reason}"}


def permission(cfg, hook):
    """PermissionRequest: allow or deny a tool call."""
    tool, inp = hook["tool_name"], hook.get("tool_input", {})
    if tool in ("AskUserQuestion", "ExitPlanMode"):
        return None  # question() answers AskUserQuestion; plan approval stays on the Mac
    detail = inp.get("command") or inp.get("file_path") or inp.get("url") or json.dumps(inp)
    what = f"{inp['description']}\n" if inp.get("description") else ""
    text = (f"{tool} in {project(hook)}:\n{what}{detail[:600]}\n\n"
            "React \N{THUMBS UP SIGN} or reply y to allow; \N{THUMBS DOWN SIGN}, n or a reason to deny.")
    decision = ask(cfg, text, lambda reply, target: decide(reply.text) if reply.text else None,
                   confirm=lambda d: "Allowed" if d["behavior"] == "allow" else d["message"])
    return decision and {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                                "decision": decision}}


def pick(q, row):
    """Option numbers (several for multi-select) or an option's label become the label; anything else
    is a free answer."""
    labels = [o["label"] for o in q["options"]]
    nums = [n.strip() for n in row.split(",")]
    if all(n.isdigit() and 1 <= int(n) <= len(labels) for n in nums) and (q.get("multiSelect") or len(nums) == 1):
        return ", ".join(labels[int(n) - 1] for n in nums)
    return next((label for label in labels if label.lower() == row.lower()), row)


def question(cfg, hook):
    """PreToolUse on AskUserQuestion: answer the questions."""
    qs = hook["tool_input"]["questions"]
    lines = [f"Question from {project(hook)}:"]
    for i, q in enumerate(qs, 1):
        lines.append(f"\n{i}. {q['question']}" + (" (several: 1,3)" if q.get("multiSelect") else ""))
        lines += [f"  {j}) {o['label']}" + (f" - {o['description']}" if o.get("description") else "")
                  for j, o in enumerate(q["options"], 1)]
    lines.append("\nTap the poll below, or reply with an option number or your own answer"
                 + (" (one line per question, or quote a question's poll)." if len(qs) > 1 else "."))
    got = {}

    def parse(reply, target):
        """Answers arrive in any order: a poll vote, a reply quoting a poll, or lines for the open questions."""
        if target is not None:
            q = qs[target]
            if reply.votes is not None:
                got[q["question"]] = ", ".join(q["options"][i]["label"] for i in sorted(set(reply.votes))
                                               if i < len(q["options"]))
            else:
                got[q["question"]] = pick(q, reply.text)
        elif reply.text:
            todo = [q for q in qs if q["question"] not in got]
            rows = [reply.text] if len(todo) == 1 else [r.strip() for r in reply.text.splitlines() if r.strip()]
            if not todo or len(rows) > len(todo):
                return None
            got.update({q["question"]: pick(q, row) for q, row in zip(todo, rows)})
        else:
            return None
        return dict(got) if len(got) == len(qs) else PARTIAL

    polls = [(f"({i}/{len(qs)}) {q['question']}" if len(qs) > 1 else q["question"],
              [o["label"] for o in q["options"]], bool(q.get("multiSelect")))
             for i, q in enumerate(qs, 1)]
    answers = ask(cfg, "\n".join(lines), parse, polls,
                  confirm=lambda a: "; ".join(f"{k} \N{RIGHTWARDS ARROW} {v}" for k, v in a.items()))
    return answers and {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "updatedInput": {**hook["tool_input"], "answers": answers}}}


def notify(cfg, hook):
    """Notification (idle_prompt): tell the owner a session is waiting."""
    if presence.away(cfg):
        Daemon(cfg).send(f"{project(hook)}: {hook.get('message', 'Claude is waiting for you')}")


def start(cfg, hook):
    """SessionStart: start the signal-cli daemon unless one is already up."""
    daemon = Daemon(cfg)
    if not daemon.is_up():
        daemon.start()


HANDLERS = {"start": start, "permission": permission, "question": question, "notify": notify}


def main(argv=sys.argv):
    """Run the handler named by argv[1] on the hook JSON from stdin; print its output, if any."""
    cfg = Config.load()
    if not cfg:
        return
    try:
        out = HANDLERS[argv[1]](cfg, json.load(sys.stdin))
    except OSError as e:
        print(f"signal-plugin-cc: signal-cli daemon on port {cfg.port}: {e}", file=sys.stderr)
        return
    except Exception:
        traceback.print_exc()  # a relay failure must never block the session
        return
    if out:
        print(json.dumps(out))
