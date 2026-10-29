"""The prompts the relay sends, and how each reads replies into an answer.

A form has text (the message), polls (sent beside it), parse(reply, target) and receipt(value).
parse gets each reply addressed to the prompt, with target the index of the poll it votes in or quotes,
or None. It returns the answer, PARTIAL while answers are missing, or None for a reply it can't read.
"""
import json
import re

from .model import PARTIAL, Poll

YES = {"y", "yes", "ok", "allow", "\N{THUMBS UP SIGN}"}
NO = {"n", "no", "deny", "\N{THUMBS DOWN SIGN}"}
SKIN_TONES = re.compile("[\U0001F3FB-\U0001F3FF️]")  # 👍🏽 counts as 👍


def decide(text):
    word = SKIN_TONES.sub("", text).lower()
    if word in YES:
        return {"behavior": "allow"}
    reason = "" if word in NO else f": {text}"
    return {"behavior": "deny", "message": f"Denied from Signal{reason}"}


def pick(question, row):
    """Option numbers (several for multi-select) or an option's label become the label; anything else
    is a free answer."""
    labels = [o["label"] for o in question["options"]]
    nums = [n.strip() for n in row.split(",")]
    if all(n.isdigit() and 1 <= int(n) <= len(labels) for n in nums) \
            and (question.get("multiSelect") or len(nums) == 1):
        return ", ".join(labels[int(n) - 1] for n in nums)
    return next((label for label in labels if label.lower() == row.lower()), row)


class PermissionForm:
    """Allow or deny a tool call: a 👍 or 👎 reaction, y, n, or a reason that denies."""
    polls = ()

    def __init__(self, tool, tool_input, project):
        detail = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("url") \
            or json.dumps(tool_input)
        what = f"{tool_input['description']}\n" if tool_input.get("description") else ""
        self.text = (f"{tool} in {project}:\n{what}{detail[:600]}\n\n"
                     "React \N{THUMBS UP SIGN} or reply y to allow; \N{THUMBS DOWN SIGN}, n or a reason to deny.")

    def parse(self, reply, target):
        return decide(reply.text) if reply.text else None

    def receipt(self, decision):
        return "Allowed" if decision["behavior"] == "allow" else decision["message"]


class QuestionForm:
    """Answer AskUserQuestion: poll votes, replies quoting a question's poll, or lines for the open
    questions, in any order."""

    def __init__(self, questions, project):
        self.questions = questions
        self.got = {}
        lines = [f"Question from {project}:"]
        for i, q in enumerate(questions, 1):
            lines.append(f"\n{i}. {q['question']}" + (" (several: 1,3)" if q.get("multiSelect") else ""))
            lines += [f"  {j}) {o['label']}" + (f" - {o['description']}" if o.get("description") else "")
                      for j, o in enumerate(q["options"], 1)]
        lines.append("\nTap the poll below, or reply with an option number or your own answer"
                     + (" (one line per question, or quote a question's poll)." if len(questions) > 1 else "."))
        self.text = "\n".join(lines)
        n = len(questions)
        self.polls = [Poll(f"({i}/{n}) {q['question']}" if n > 1 else q["question"],
                           [o["label"] for o in q["options"]], bool(q.get("multiSelect")))
                      for i, q in enumerate(questions, 1)]

    def parse(self, reply, target):
        if target is not None:
            q = self.questions[target]
            if reply.votes is not None:
                self.got[q["question"]] = ", ".join(q["options"][i]["label"] for i in sorted(set(reply.votes))
                                                    if i < len(q["options"]))
            else:
                self.got[q["question"]] = pick(q, reply.text)
        elif reply.text:
            todo = [q for q in self.questions if q["question"] not in self.got]
            rows = [reply.text] if len(todo) == 1 else [r.strip() for r in reply.text.splitlines() if r.strip()]
            if not todo or len(rows) > len(todo):
                return None
            self.got.update({q["question"]: pick(q, row) for q, row in zip(todo, rows)})
        else:
            return None
        return dict(self.got) if len(self.got) == len(self.questions) else PARTIAL

    def receipt(self, answers):
        return "; ".join(f"{q} \N{RIGHTWARDS ARROW} {a}" for q, a in answers.items())


class ContinueForm:
    """A finished turn's last message; any reply continues the session."""
    polls = ()
    LIMIT = 1500

    def __init__(self, last_message, project):
        last = (last_message or "Finished its turn.").strip()
        if len(last) > self.LIMIT:
            last = last[:self.LIMIT] + "\N{HORIZONTAL ELLIPSIS}"
        self.project = project
        self.text = f"{project}:\n{last}\n\nReply to continue this session."

    def parse(self, reply, target):
        return reply.text or None

    def receipt(self, _):
        return f"Sent to {self.project}"
