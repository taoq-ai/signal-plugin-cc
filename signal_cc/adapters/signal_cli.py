"""Messenger over the signal-cli HTTP daemon (signal-cli-jsonrpc(5)), plus the daemon's lifecycle."""
import http.client
import json
import queue
import subprocess
import threading
import urllib.request

from ..domain.model import Reply


class SignalCli:
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

    def _call(self, method, params):
        # notifySelf sends Note to Self as a normal message, so the phone notifies
        to = {"noteToSelf": True, "notifySelf": True} if self.cfg.note_to_self else {"recipient": [self.cfg.owner]}
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": {**to, **params}}).encode()
        req = urllib.request.Request(f"{self.base}/rpc", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.load(r)
        if "error" in out:
            raise RuntimeError(f"{method}: {out['error'].get('message', out['error'])}")
        return out["result"]

    def send(self, text):
        return self._call("send", {"message": text})["timestamp"]

    def send_poll(self, question, options, multi):
        return self._call("sendPollCreate", {"question": question, "option": options, "noMulti": not multi})["timestamp"]

    def end_poll(self, ts):
        self._call("sendPollTerminate", {"pollTimestamp": ts, "notifySelf": False})  # quietly

    def subscribe(self):
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
            for line in resp:
                reply = self.parse_event(line)
                if reply:
                    out.put(reply)
        except (OSError, ValueError, AttributeError):
            pass  # closed under us
        finally:
            out.put(None)  # the stream ended

    def parse_event(self, line):
        """The Reply an event-stream line carries from the owner, or None."""
        if not line.startswith(b"data:"):
            return None
        try:
            event = json.loads(line[5:])
        except ValueError:
            return None
        env = event.get("params", event).get("envelope", {})
        if env.get("sourceNumber", env.get("source")) != self.cfg.owner:
            return None
        # on your own account, what you send to Note to Self arrives as a sync of a sent message
        sent = (env.get("syncMessage") or {}).get("sentMessage") or {}
        to_self = sent.get("destinationNumber", sent.get("destination")) == self.cfg.owner
        msg = sent if to_self else env.get("dataMessage") or {}
        vote = msg.get("pollVote") or {}
        reaction = msg.get("reaction") or {}
        if vote.get("optionIndexes"):  # an empty list is a withdrawn vote
            return Reply("", vote.get("targetSentTimestamp"), vote["optionIndexes"])
        if reaction.get("emoji") and not reaction.get("isRemove"):
            return Reply(reaction["emoji"], reaction.get("targetSentTimestamp"))
        if msg.get("message"):
            return Reply(msg["message"].strip(), (msg.get("quote") or {}).get("id"))
        return None
