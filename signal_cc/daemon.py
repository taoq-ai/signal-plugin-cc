"""Client for the signal-cli HTTP daemon (signal-cli-jsonrpc(5))."""
import http.client
import json
import queue
import subprocess
import threading
import urllib.request
from collections import namedtuple

# What the owner sent: text (a message or a reaction's emoji), the timestamp of the message it quotes,
# reacts to or votes in, and for a poll vote the chosen option indexes.
Reply = namedtuple("Reply", "text quoted votes", defaults=(None, None))


class Daemon:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base = f"http://127.0.0.1:{cfg.port}/api/v1"

    def is_up(self):
        try:
            urllib.request.urlopen(f"{self.base}/check", timeout=2).close()
            return True
        except OSError:
            return False

    def start(self):
        """Start the daemon in the background, logging to <home>/daemon.log."""
        self.cfg.home.mkdir(parents=True, exist_ok=True)
        with open(self.cfg.home / "daemon.log", "ab") as log:
            subprocess.Popen(
                [self.cfg.signal_cli, "-a", self.cfg.account, "daemon", "--http", f"127.0.0.1:{self.cfg.port}"],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)

    def _call(self, method, params, tag=None):
        """Call method addressed to the owner and return its result.

        tag names the prompt the message belongs to (empty for none); it is recorded before sending,
        so a plain reply only ever counts for the latest message (ask.latest). None records nothing.
        """
        if tag is not None:
            (self.cfg.home / "last").write_text(tag)
        # notifySelf sends Note to Self as a normal message, so the phone notifies
        to = {"noteToSelf": True, "notifySelf": True} if self.cfg.note_to_self else {"recipient": [self.cfg.owner]}
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": {**to, **params}}).encode()
        req = urllib.request.Request(f"{self.base}/rpc", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.load(r)
        if "error" in out:
            raise RuntimeError(f"{method}: {out['error'].get('message', out['error'])}")
        return out["result"]

    def send(self, text, tag=""):
        """Send text; return the timestamp a reply quotes."""
        return self._call("send", {"message": text}, tag)["timestamp"]

    def send_poll(self, question, options, multi, tag=""):
        """Send a poll; return the timestamp its votes point at."""
        return self._call("sendPollCreate", {"question": question, "option": options, "noMulti": not multi},
                          tag)["timestamp"]

    def end_poll(self, ts):
        """Close a poll quietly, so it shows as answered."""
        self._call("sendPollTerminate", {"pollTimestamp": ts, "notifySelf": False})

    def subscribe(self):
        """Open the event stream; return (queue of Reply from the owner, close)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.cfg.port, timeout=10)
        conn.connect()
        sock = conn.sock  # getresponse may drop conn.sock on a close-delimited stream
        conn.request("GET", "/api/v1/events")
        resp = conn.getresponse()
        sock.settimeout(None)
        replies = queue.Queue()
        threading.Thread(target=self._read, args=(resp, replies), daemon=True).start()
        return replies, conn.close

    def _read(self, resp, out):
        try:
            self._read_lines(resp, out)
        except (OSError, ValueError, AttributeError):
            pass  # ask() closed the stream under us

    def _read_lines(self, resp, out):
        for line in resp:
            if not line.startswith(b"data:"):
                continue
            try:
                event = json.loads(line[5:])
            except ValueError:
                continue
            env = event.get("params", event).get("envelope", {})
            # on your own account, what you send to Note to Self arrives as a sync of a sent message
            sent = (env.get("syncMessage") or {}).get("sentMessage") or {}
            to_self = sent.get("destinationNumber", sent.get("destination")) == self.cfg.owner
            msg = sent if to_self else env.get("dataMessage") or {}
            if env.get("sourceNumber", env.get("source")) != self.cfg.owner:
                continue
            vote = msg.get("pollVote") or {}
            reaction = msg.get("reaction") or {}
            if vote.get("optionIndexes"):  # an empty list is a withdrawn vote
                out.put(Reply("", vote.get("targetSentTimestamp"), vote["optionIndexes"]))
            elif reaction.get("emoji") and not reaction.get("isRemove"):
                out.put(Reply(reaction["emoji"], reaction.get("targetSentTimestamp")))
            elif msg.get("message"):
                out.put(Reply(msg["message"].strip(), (msg.get("quote") or {}).get("id")))
