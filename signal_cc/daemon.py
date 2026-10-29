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
                [self.cfg.signal_cli, "-a", self.cfg.bot, "daemon", "--http", f"127.0.0.1:{self.cfg.port}"],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)

    def send(self, text):
        """Send text to the owner and return the message timestamp Signal quotes in replies."""
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "send",
                           "params": {"recipient": [self.cfg.owner], "message": text}}).encode()
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
        for line in resp:
            if not line.startswith(b"data:"):
                continue
            event = json.loads(line[5:])
            env = event.get("params", event).get("envelope", {})
            msg = env.get("dataMessage") or {}
            if env.get("sourceNumber", env.get("source")) == self.cfg.owner and msg.get("message"):
                out.put((msg["message"].strip(), (msg.get("quote") or {}).get("id")))
