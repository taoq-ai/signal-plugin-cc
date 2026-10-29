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
