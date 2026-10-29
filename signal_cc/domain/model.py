"""The values the relay passes around."""
from collections import namedtuple

# What the owner sent: text (a message or a reaction's emoji), the timestamp of the message it quotes,
# reacts to or votes in, and for a poll vote the chosen option indexes.
Reply = namedtuple("Reply", "text quoted votes", defaults=(None, None))

# A prompt that waits for the owner: when it was sent, its tag, and the first line of its text.
Waiting = namedtuple("Waiting", "created tag summary")

# A poll beside a prompt's text: the question, the option labels, and whether several may be picked.
Poll = namedtuple("Poll", "question options multi")

PARTIAL = object()  # a form took the reply, but answers are still missing

# Why hooks.quiet stopped a session's listener, each also the relay.log outcome of the prompt it held
AT_MAC = "answered at the Mac"  # the owner typed a prompt in the session at the Mac
CLOSED = "session closed"


class Stopped(SystemExit):
    """The session's listener was stopped: AT_MAC, CLOSED, or None when a new turn replaced it.
    Exits with status 0, so the session is not woken."""

    def __init__(self, why=None):
        super().__init__(0)
        self.why = why
