"""The use cases: ask the owner over Signal, and continue a finished session from Signal."""
import queue
import time

from ..domain import texts
from ..domain.model import PARTIAL
from ..domain.routing import HINT, SKIP, route

SETTLE = 5  # seconds to let taps on a multi-select poll settle before answering
POLL = 5  # seconds between presence checks while a finished session waits for the owner to leave


class Conversation:
    def __init__(self, messenger, registry, presence, wait, journal, session):
        self.messenger = messenger
        self.registry = registry
        self.presence = presence
        self.wait = wait  # seconds a prompt waits for a reply
        self.journal = journal
        self.session = session  # the Claude Code session that asks, for the journal

    def say(self, tag, text):
        """Send text that belongs to the prompt tagged tag (None: record nothing)."""
        if tag is not None:
            self.registry.mark_latest(tag)  # before sending, so a fast plain reply finds it
        return self.messenger.send(text)

    def ask(self, form, wait=None, leave_on_return=True):
        """Send the form and its polls; return its answer.

        None when the owner is at the Mac, on timeout, when the event stream ends, or (with
        leave_on_return) when the owner comes back to the Mac.
        """
        if not self.presence.away():
            return None
        end, started = {"tag": None, "outcome": "send failed"}, time.time()
        try:
            return self._ask(form, wait or self.wait, leave_on_return, end)
        finally:  # one line per prompt, however it ends; never the text or who it went to
            self.journal.record({"kind": form.kind, "tag": end["tag"], "session": self.session,
                                 "outcome": end["outcome"], "waited": round(time.time() - started, 1)})

    def _ask(self, form, wait, leave_on_return, end):
        """ask, noting in end the prompt's tag and how it ended."""
        replies, close = self.messenger.subscribe()  # before sending, so no reply is missed
        tag = end["tag"] = self.registry.claim(form.text.splitlines()[0], wait)
        sent = {}  # timestamp of each message of this prompt -> the poll index it holds, or None
        try:
            sent[self.say(tag, texts.tagged(tag, form.text))] = None
            end["outcome"] = "error"  # until _collect names the end
            for i, poll in enumerate(form.polls):
                try:
                    self.registry.mark_latest(tag)
                    sent[self.messenger.send_poll(texts.tagged(tag, poll.question)[:200], poll.options,
                                                  poll.multi)] = i
                except RuntimeError:
                    break  # the text message still takes replies
            return self._collect(form, tag, sent, replies, time.time() + wait, leave_on_return, end)
        finally:
            self.registry.release(tag)
            for ts, poll in sent.items():
                if poll is not None:
                    try:
                        self.messenger.end_poll(ts)
                    except (OSError, RuntimeError):
                        pass
            close()

    def _collect(self, form, tag, sent, replies, deadline, leave_on_return, end):
        value, settle = None, 0
        while time.time() < deadline:
            if value is not None and time.time() >= settle:
                break
            try:
                reply = replies.get(timeout=2 if value is None else max(0.1, settle - time.time()))
            except queue.Empty:
                if value is None and leave_on_return and self.presence.returned():
                    end["outcome"] = "back at the Mac"
                    self.say(tag, texts.tagged(tag, texts.BACK_AT_MAC))
                    return None
                continue
            if reply is None:
                end["outcome"] = "stream ended" if value is None else "answered"
                return value  # the stream ended
            where = route(reply, tag, sent, self.registry.waiting(), self.registry.latest())
            if where == HINT:
                text, hint_tag = texts.hint(self.registry.waiting())
                self.say(hint_tag, text)
            if where in (HINT, SKIP):
                continue
            result = form.parse(where.reply, where.target)
            if result is None:
                sent[self.say(tag, texts.tagged(tag, texts.UNREADABLE))] = None
            elif result is not PARTIAL:
                value = result
                if where.reply.votes is not None and form.polls[where.target].multi:
                    settle = max(settle, time.time() + SETTLE)
        end["outcome"] = "timed out" if value is None else "answered"
        if value is None:
            self.say(tag, texts.tagged(tag, texts.TIMED_OUT))
        else:
            self.say(None, texts.tagged(tag, f"{texts.CHECK} {form.receipt(value)}"))  # the prompt is done
        return value


def continue_session(conversation, form, grace, wait):
    """A turn ended: once the owner is away, send its last message and return their reply.

    If the owner stays at the Mac for grace seconds, they saw the result there: None, nothing sent.
    """
    deadline = time.time() + grace
    while not conversation.presence.away():
        if time.time() > deadline:
            return None
        time.sleep(POLL)
    return conversation.ask(form, wait=wait, leave_on_return=False)
