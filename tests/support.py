"""Test doubles: in-memory fakes for the ports, and a stub signal-cli HTTP daemon for the adapters."""
import json
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signal_cc.domain import texts  # noqa: E402
from signal_cc.domain.model import Reply, Waiting  # noqa: E402

OWNER = "+15550000001"


class FakeMessenger:
    """Records what is sent. script holds one callable per message sent, (text, ts) -> a Reply to receive
    next, or None; receipts and timeouts take no script entry."""

    def __init__(self, *script):
        self.sent, self.ended, self.script = [], [], list(script)
        self.replies = queue.Queue()
        self.fail_polls = False
        self.fail_sends = False
        self.ts = 1000

    def _out(self, text):
        if self.fail_sends:
            raise OSError("connection refused")
        self.ts += 1
        self.sent.append(text)
        if self.script and texts.CHECK not in text and texts.TIMED_OUT not in text:
            reply = self.script.pop(0)(text, self.ts)
            if reply:
                self.replies.put(reply)
        return self.ts

    def send(self, text):
        return self._out(text)

    def send_poll(self, question, options, multi):
        if self.fail_polls:
            raise RuntimeError("poll refused")
        return self._out(f"POLL {question} {options} multi={multi}")

    def end_poll(self, ts):
        self.ended.append(ts)

    def subscribe(self):
        return self.replies, lambda: None


class FakeRegistry:
    def __init__(self, *others):
        self.live = {w.tag: w for w in others}
        self.expires = {}  # tag -> when its claim lapses; others never do
        self.last = ""
        self.n = 0
        self.kept = {}  # session -> [(tag, ts)] of its earlier turns' messages

    def claim(self, summary, ttl):
        self.n += 1
        tag = f"{self.n:04x}"
        self.live[tag] = Waiting(10_000_000_000 + self.n, tag, summary)  # newer than any test fixture
        self.expires[tag] = time.time() + ttl
        return tag

    def release(self, tag):
        self.live.pop(tag, None)

    def waiting(self):
        return sorted(w for w in self.live.values() if self.expires.get(w.tag, float("inf")) > time.time())

    def latest(self):
        return self.last

    def mark_latest(self, tag):
        self.last = tag

    def keep(self, session, tag, ts):
        self.kept.setdefault(session, []).append((tag, ts))

    def threads(self):
        return {session: list(messages) for session, messages in self.kept.items()}

    def forget(self, session):
        self.kept.pop(session, None)


class FakeJournal:
    def __init__(self):
        self.lines = []

    def record(self, entry):
        self.lines.append(entry)


class FakePresence:
    def __init__(self, away=True, returned=False):
        self._away, self._returned = away, returned
        self.switch = False

    def set_switch(self, on):
        self.switch = on

    def switch_on(self):
        return self.switch

    def away(self):
        return self._away

    def returned(self):
        return self._returned


def quoting(text):
    """A script entry: reply with text, quoting the message it answers."""
    return lambda m, ts: Reply(text, ts)


def plain(text):
    return lambda m, ts: Reply(text)


class StubDaemon(BaseHTTPRequestHandler):
    """A signal-cli HTTP daemon: records calls; events() is fed by the test. Start with serve()."""
    calls, events, fail_polls = [], queue.Queue(), False

    @classmethod
    def reset(cls):
        cls.calls, cls.events, cls.fail_polls = [], queue.Queue(), False

    @classmethod
    def push(cls, envelope):
        cls.events.put({"jsonrpc": "2.0", "method": "receive", "params": {"envelope": envelope}})

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        if self.path.endswith("/events"):
            events = StubDaemon.events  # this test's queue
            while (event := events.get()) is not None:
                self.wfile.write(b"event:receive\ndata:" + json.dumps(event).encode() + b"\n\n")
                self.wfile.flush()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        StubDaemon.calls.append((body["method"], body["params"]))
        if body["method"] == "sendPollCreate" and StubDaemon.fail_polls:
            out = {"error": {"code": -1, "message": "poll too long"}}
        else:
            out = {"result": {"timestamp": 1000 + len(StubDaemon.calls)}}
        data = json.dumps({"jsonrpc": "2.0", "id": body["id"], **out}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def serve():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubDaemon)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
