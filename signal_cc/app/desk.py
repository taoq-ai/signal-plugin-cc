"""The desk use case: answer commands sent from Signal while nothing else is listening."""
import time

from ..domain import texts
from ..domain.routing import command


def serve(messenger, registry, presence):
    """Answer commands until the event stream ends. Replies to prompts are left to the prompts."""
    replies, close = messenger.subscribe()
    try:
        while (reply := replies.get()) is not None:
            word = command(reply)
            if word == "status":
                text, tag = texts.status(registry.waiting(), time.time(), presence.switch_on())
                registry.mark_latest(tag)  # a plain reply to the status is for the one prompt it lists
                messenger.send(text)
            elif word in ("away", "back"):
                presence.set_switch(word == "away")
                registry.mark_latest("")  # a plain reply to the confirmation is for no prompt
                messenger.send(texts.AWAY_ON if word == "away" else texts.AWAY_OFF)
    finally:
        close()
