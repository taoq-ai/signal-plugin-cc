"""Which prompt a reply belongs to. Replies never cross between sessions.

A reply counts for a prompt only when it quotes or reacts to one of the prompt's messages, starts with
its tag, or is a plain reply while the prompt is the only one waiting and the latest message the relay
sent belongs to it. For any other plain reply, the oldest waiting prompt sends one hint.

A digest lists several finished sessions in one message and a poll. Its members share both: a reply
quoting or reacting to them names no session, so the oldest waiting member sends the hint; a vote in the
poll shows the picked session's full message; a tag of a member the Mac took over gets told so, and a tag
of any other member that no longer waits (just answered by this very reply, say) is left alone.
"""
import re
from collections import namedtuple

from .model import Digest

COMMANDS = {"status", "away", "back"}  # answered by the desk, never taken as a reply
TAGGED = re.compile(r"\[?([0-9a-f]{4})\]?(?:\s+|$)(.*)", re.I | re.S)

Take = namedtuple("Take", "reply target")  # the reply is for this prompt; target is the poll index, or None
SKIP = "skip"  # the reply is for another prompt, or for none
HINT = "hint"  # the reply is ambiguous, and this prompt is the one to say so
SHOW = "show"  # the owner picked this prompt in a digest's poll: send its full message
Gone = namedtuple("Gone", "tag")  # the reply is tagged for a digest member that no longer waits; say so


def command(reply):
    """The command a reply is, or None. Only a plain message counts, never one quoting a prompt."""
    word = reply.text.strip().lower()
    return word if reply.quoted is None and reply.votes is None and word in COMMANDS else None


def route(reply, me, sent, live, latest, gone=()):
    """Where a reply goes, seen from the prompt tagged me.

    sent maps the timestamp of each of my messages to the poll it holds (None for text); live is the
    waiting prompts, oldest first; latest is the tag of the prompt the relay's latest message belongs to;
    gone is the tags of digest members the Mac took over.
    """
    if command(reply):
        return SKIP
    tagged = TAGGED.match(reply.text)
    if tagged and tagged.group(1).lower() in {w.tag for w in live}:
        if tagged.group(1).lower() != me:
            return SKIP
        return Take(reply._replace(text=tagged.group(2).strip()), None)
    if tagged:  # a tag of a digest member that no longer waits
        for digest in (d for d in sent.values() if isinstance(d, Digest)):
            if tagged.group(1).lower() in digest.tags:
                taken = tagged.group(1).lower() in gone and oldest(digest, live) == me
                return Gone(tagged.group(1).lower()) if taken else SKIP
    if reply.quoted is not None:
        where = sent.get(reply.quoted, SKIP)
        if not isinstance(where, Digest):
            return SKIP if where is SKIP else Take(reply, where)
        if where.poll is not None and reply.votes is not None:
            return SHOW if {where.poll[i] for i in reply.votes if i < len(where.poll)} == {me} else SKIP
        return HINT if oldest(where, live) == me else SKIP
    if any(w.tag != me for w in live) or latest != me:
        return HINT if live and live[0].tag == me else SKIP
    return Take(reply, None)


def oldest(digest, live):
    """The tag of the digest's oldest member still waiting ("" for none)."""
    return next((w.tag for w in live if w.tag in digest.tags), "")
