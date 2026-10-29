"""Which prompt a reply belongs to. Replies never cross between sessions.

A reply counts for a prompt only when it quotes or reacts to one of the prompt's messages, starts with
its tag, or is a plain reply while the prompt is the only one waiting and the latest message the relay
sent belongs to it. For any other plain reply, the oldest waiting prompt sends one hint.
"""
import re
from collections import namedtuple

COMMANDS = {"status", "away", "back"}  # answered by the desk, never taken as a reply
TAGGED = re.compile(r"\[?([0-9a-f]{4})\]?(?:\s+|$)(.*)", re.I | re.S)

Take = namedtuple("Take", "reply target")  # the reply is for this prompt; target is the poll index, or None
SKIP = "skip"  # the reply is for another prompt, or for none
HINT = "hint"  # the reply is ambiguous, and this prompt is the one to say so


def command(reply):
    """The command a reply is, or None. Only a plain message counts, never one quoting a prompt."""
    word = reply.text.strip().lower()
    return word if reply.quoted is None and reply.votes is None and word in COMMANDS else None


def route(reply, me, sent, live, latest):
    """Where a reply goes, seen from the prompt tagged me.

    sent maps the timestamp of each of my messages to the poll it holds (None for text); live is the
    waiting prompts, oldest first; latest is the tag of the prompt the relay's latest message belongs to.
    """
    if command(reply):
        return SKIP
    tagged = TAGGED.match(reply.text)
    if tagged and tagged.group(1).lower() in {w.tag for w in live}:
        if tagged.group(1).lower() != me:
            return SKIP
        return Take(reply._replace(text=tagged.group(2).strip()), None)
    if reply.quoted is not None:
        return Take(reply, sent[reply.quoted]) if reply.quoted in sent else SKIP
    if any(w.tag != me for w in live) or latest != me:
        return HINT if live and live[0].tag == me else SKIP
    return Take(reply, None)
