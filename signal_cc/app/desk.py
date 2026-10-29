"""The desk use case: answer commands sent from Signal while nothing else is listening."""
import time

from ..domain import texts
from ..domain.routing import command


def serve(messenger, registry):
    """Answer commands until the event stream ends. Replies to prompts are left to the prompts."""
    replies, close = messenger.subscribe()
    try:
        while (reply := replies.get()) is not None:
            if command(reply) == "status":
                text, tag = texts.status(registry.waiting(), time.time())
                registry.mark_latest(tag)  # a plain reply to the status is for the one prompt it lists
                messenger.send(text)
    finally:
        close()
