"""Client for the signal-cli HTTP daemon (signal-cli-jsonrpc(5))."""
import http.client
import json
import queue
import subprocess
import threading
import urllib.request


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

    def send(self, text, tag=""):
        """Send text to the owner and return the message timestamp Signal quotes in replies.

        tag names the prompt the message belongs to (empty for none); it is recorded before sending,
        so a plain reply only ever counts for the latest message (ask.latest).
        """
        (self.cfg.home / "last").write_text(tag)
        # notifySelf sends Note to Self as a normal message, so the phone notifies
        to = {"noteToSelf": True, "notifySelf": True} if self.cfg.note_to_self else {"recipient": [self.cfg.owner]}
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "send",
                           "params": {**to, "message": text}}).encode()
        req = urllib.request.Request(f"{self.base}/rpc", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["result"]["timestamp"]

    def subscribe(self):
        """Open the event stream; return (queue of (text, quoted timestamp) from the owner, close)."""
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
            # on your own account, what you type into Note to Self arrives as a sync of a sent message
            sent = (env.get("syncMessage") or {}).get("sentMessage") or {}
            to_self = sent.get("destinationNumber", sent.get("destination")) == self.cfg.owner
            msg = sent if to_self else env.get("dataMessage") or {}
            if env.get("sourceNumber", env.get("source")) != self.cfg.owner:
                continue
            reaction = msg.get("reaction") or {}
            if reaction.get("emoji") and not reaction.get("isRemove"):
                # a reaction answers with its emoji, addressed to the message it reacts to
                out.put((reaction["emoji"], reaction.get("targetSentTimestamp")))
            elif msg.get("message"):
                out.put((msg["message"].strip(), (msg.get("quote") or {}).get("id")))
