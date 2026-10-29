"""The use cases: ask the owner over Signal, and continue a finished session from Signal."""
import queue
import time

from ..domain import texts
from ..domain.model import PARTIAL, Digest
from ..domain.routing import HINT, SHOW, SKIP, Gone, route

SETTLE = 5  # seconds to let taps on a multi-select poll settle before answering
POLL = 5  # seconds between presence checks while a finished session waits for the owner to leave
GATHER = 10  # seconds the first finished session to see the owner leave waits for the others to join its digest
STEP = 0.5  # seconds between checks while another session gathers a digest


class Conversation:
    def __init__(self, messenger, registry, presence, wait, journal, session, gathering=None):
        self.messenger = messenger
        self.registry = registry
        self.presence = presence
        self.wait = wait  # seconds a prompt waits for a reply
        self.journal = journal
        self.session = session  # the Claude Code session that asks, for the journal
        self.gathering = gathering  # None: a finished session never joins a digest

    def say(self, tag, text):
        """Send text that belongs to the prompt tagged tag (None: record nothing)."""
        if tag is not None:
            self.registry.mark_latest(tag)  # before sending, so a fast plain reply finds it
        return self.messenger.send(text)

    def ask(self, form, wait=None, leave_on_return=True, gather=False):
        """Send the form and its polls; return its answer.

        None when the owner is at the Mac, on timeout, when the event stream ends, or (with
        leave_on_return) when the owner comes back to the Mac. With gather (a ContinueForm), the form may
        go out in one digest with the other sessions that finished at the same time.
        """
        if not self.presence.away():
            return None
        end, started = {"tag": None, "outcome": "error"}, time.time()
        try:
            return self._ask(form, wait or self.wait, leave_on_return, end, gather and self.gathering)
        except SystemExit:  # the session's listener was stopped (hooks.quiet): a normal end, not a failure
            if end["outcome"] in ("error", "send failed"):
                end["outcome"] = "quieted"
            raise
        finally:  # one line per prompt, however it ends; never the text or who it went to
            self.journal.record({"kind": form.kind, "tag": end["tag"], "session": self.session,
                                 "outcome": end["outcome"], "waited": round(time.time() - started, 1),
                                 **({"digest": end["digest"]} if "digest" in end else {})})

    def _ask(self, form, wait, leave_on_return, end, gathering):
        """ask, noting in end the prompt's tag and how it ended."""
        replies, close = self.messenger.subscribe()  # before sending, so no reply is missed
        tag = end["tag"] = self.registry.claim(form.text.splitlines()[0], wait)
        sent = {}  # timestamp of each message of this prompt -> the poll index it holds, None, or a Digest
        try:
            end["outcome"] = "send failed"
            sent.update(self._gather(form, tag, gathering, end) if gathering else {})
            if not sent:
                sent[self.say(tag, texts.tagged(tag, form.text))] = None
                if gathering:
                    gathering.update(tag, sent=time.time())  # a later digest points at this message
            end["outcome"] = "error"  # until _collect names the end
            for i, poll in enumerate(form.polls):
                try:
                    self.registry.mark_latest(tag)
                    sent[self.messenger.send_poll(texts.tagged(tag, poll.question)[:200], poll.options,
                                                  poll.multi)] = i
                except RuntimeError:
                    break  # the text message still takes replies
            return self._collect(form, tag, sent, replies, time.time() + wait, leave_on_return, end)
        except SystemExit as stopped:  # hooks.quiet: tell Signal if the Mac took over a prompt still waiting
            why = getattr(stopped, "why", None)
            if why and sent and end["outcome"] == "error":
                end["outcome"] = why
                if gathering:
                    gathering.update(tag, gone=why)  # a reply tagged for it from the digest gets told so
                try:
                    self.say(None, texts.tagged(tag, texts.STOPPED[why]))
                except (OSError, RuntimeError):
                    pass  # the listener exits either way
            raise
        finally:
            self.registry.release(tag)
            if gathering and not (gathering.entries().get(tag) or {}).get("gone"):
                gathering.leave(tag)  # a gone entry stays until the next digest's lead clears it
            waiting = {w.tag for w in self.registry.waiting()} if any(isinstance(p, Digest) for p in sent.values()) \
                else set()
            for ts, poll in sent.items():
                if isinstance(poll, Digest):  # the last member still waiting closes the digest's poll
                    poll = None if poll.poll is None or waiting & set(poll.tags) else poll.poll
                if poll is not None:
                    try:
                        self.messenger.end_poll(ts)
                    except (OSError, RuntimeError):
                        pass
            close()

    def _gather(self, form, tag, gathering, end):
        """Join one digest with the other sessions that finished at the same time; return the digest's messages
        as sent entries, or {} for this session to send its own message (the only one finished)."""
        gathering.enter(tag, form.project, form.first)
        while not gathering.lead():  # another session gathers: it may put this one in its digest
            digest = (gathering.entries().get(tag) or {}).get("digest")
            if digest:
                return self._joined(digest, end)
            time.sleep(STEP)
        try:
            digest = (gathering.entries().get(tag) or {}).get("digest")  # the last lead may have just put it in
            if digest:
                return self._joined(digest, end)
            time.sleep(GATHER)
            live = {w.tag for w in self.registry.waiting()}
            rows = gathering.entries()
            for t in [t for t, r in rows.items() if t not in live or r.get("gone")]:  # ended, or its listener died
                gathering.leave(t)
                del rows[t]
            rows = sorted((r["created"], t, r) for t, r in rows.items())
            members = [t for _, t, r in rows if r["sent"] is None]
            if len(members) < 2:
                return {}
            text = texts.digest([(t, r["project"], r["first"], r["sent"]) for _, t, r in rows])
            digest = {"tags": members, "text": self.say("", text), "poll": None,
                      "options": members[:texts.DIGEST_POLL_MAX]}
            projects = {t: r["project"] for _, t, r in rows}
            try:
                self.registry.mark_latest("")
                digest["poll"] = self.messenger.send_poll(
                    texts.DIGEST_POLL, [texts.option(t, projects[t]) for t in digest["options"]], False)
            except RuntimeError:
                pass  # the digest's tags still work
            now = time.time()
            for t in members:
                gathering.update(t, digest=digest, sent=now)
            return self._joined(digest, end)
        finally:
            gathering.unlead()

    @staticmethod
    def _joined(digest, end):
        """The sent entries of a digest's text and poll."""
        end["digest"] = len(digest["tags"])
        tags = tuple(digest["tags"])
        sent = {digest["text"]: Digest(tags, None)}
        if digest["poll"] is not None:
            sent[digest["poll"]] = Digest(tags, tuple(digest["options"]))
        return sent

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
            gone = {t for t, r in self.gathering.entries().items() if r.get("gone")} \
                if any(isinstance(d, Digest) for d in sent.values()) else ()
            where = route(reply, tag, sent, self.registry.waiting(), self.registry.latest(), gone)
            if isinstance(where, Gone):
                self.say("", texts.tagged(where.tag, texts.GONE))
                continue
            if where == SHOW:  # picked in a digest's poll: the full message, which a quote then answers
                sent[self.say(tag, texts.tagged(tag, form.text))] = None
                continue
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
    return conversation.ask(form, wait=wait, leave_on_return=False, gather=True)
