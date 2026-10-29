"""End-to-end checks of relay.py against a stub signal-cli HTTP daemon. Run: python3 -m unittest discover -s tests"""
import json
import queue
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import relay  # noqa: E402

OWNER = "+15550000001"


class Daemon(BaseHTTPRequestHandler):
    """Records sends; answers each prompt with the next scripted reply(message, timestamp) -> (text, quote)."""
    sent, script, events = [], [], queue.Queue()

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        if self.path.endswith("/events"):
            events = Daemon.events  # this test's queue
            while (event := events.get()) is not None:
                self.wfile.write(b"event:receive\ndata:" + json.dumps(event).encode() + b"\n\n")
                self.wfile.flush()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        message = body["params"]["message"]
        Daemon.sent.append(message)
        ts = 1000 + len(Daemon.sent)
        if Daemon.script and "Timed out" not in message:
            text, quote = Daemon.script.pop(0)(message, ts)
            msg = {"message": text, **({"quote": {"id": quote}} if quote else {})}
            Daemon.events.put({"jsonrpc": "2.0", "method": "receive",
                               "params": {"envelope": {"sourceNumber": OWNER, "dataMessage": msg}}})
        out = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {"timestamp": ts}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


def tag(message):
    return re.match(r"\[(\w+)\]", message).group(1)


class RelayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Daemon)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Daemon.sent.clear()
        Daemon.script.clear()
        Daemon.events = queue.Queue()
        self.tmp = tempfile.TemporaryDirectory()
        relay.HOME = Path(self.tmp.name)
        relay.idle_seconds = lambda: 1000  # away from the Mac
        self.cfg = {**relay.DEFAULTS, "bot": "+15550000002", "owner": OWNER,
                    "port": self.server.server_port, "wait": 10}

    def tearDown(self):
        Daemon.events.put(None)  # end the open event stream
        self.tmp.cleanup()

    def test_permission_allowed_by_quoted_reply(self):
        Daemon.script.append(lambda m, ts: ("Y", ts))
        out = relay.permission(self.cfg, {"tool_name": "Bash", "cwd": "/x/proj",
                                          "tool_input": {"command": "rm -rf build", "description": "Clean"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})
        self.assertIn("rm -rf build", Daemon.sent[0])
        self.assertIn("Bash in proj", Daemon.sent[0])

    def test_permission_denied_with_reason_by_tag(self):
        Daemon.script.append(lambda m, ts: (f"{tag(m)} use the test db", None))
        out = relay.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "psql prod"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"],
                         {"behavior": "deny", "message": "Denied from Signal: use the test db"})

    def test_unquoted_reply_skipped_while_another_prompt_waits(self):
        (relay.HOME / "pending").mkdir(parents=True)
        (relay.HOME / "pending" / "zzzz").write_text("9999999999")
        Daemon.script.append(lambda m, ts: ("y", None))
        self.cfg["wait"] = 3
        self.assertIsNone(relay.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        self.assertIn("Timed out", Daemon.sent[-1])

    def test_questions_answered_with_numbers_and_free_text(self):
        qs = [{"question": "Which db?", "header": "DB", "multiSelect": False,
               "options": [{"label": "Postgres", "description": "SQL"}, {"label": "Mongo", "description": "Docs"}]},
              {"question": "Which checks?", "header": "Checks", "multiSelect": True,
               "options": [{"label": "lint", "description": ""}, {"label": "tests", "description": ""}]},
              {"question": "Name?", "header": "Name", "multiSelect": False,
               "options": [{"label": "a", "description": ""}, {"label": "b", "description": ""}]}]
        Daemon.script += [lambda m, ts: ("2", ts),  # wrong line count: asked again
                          lambda m, ts: ("2\n1, 2\nmy own name", ts)]
        out = relay.question(self.cfg, {"tool_input": {"questions": qs}})["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(out["updatedInput"]["questions"], qs)
        self.assertEqual(out["updatedInput"]["answers"],
                         {"Which db?": "Mongo", "Which checks?": "lint, tests", "Name?": "my own name"})
        self.assertIn("Couldn't read", Daemon.sent[1])

    def test_at_the_mac_nothing_is_sent(self):
        relay.idle_seconds = lambda: 5
        self.assertIsNone(relay.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        self.assertEqual(Daemon.sent, [])

    def test_without_config_the_hook_prints_nothing(self):
        env = {"SIGNAL_CC_HOME": self.tmp.name, "PATH": "/usr/bin:/bin"}
        run = subprocess.run([sys.executable, str(ROOT / "relay.py"), "permission"], env=env,
                             input='{"tool_name": "Bash", "tool_input": {}}', capture_output=True, text=True)
        self.assertEqual((run.returncode, run.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
