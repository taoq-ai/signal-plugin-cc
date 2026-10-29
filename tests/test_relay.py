"""End-to-end checks of relay.py against a stub signal-cli HTTP daemon. Run: python3 -m unittest discover -s tests"""
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from signal_cc import hooks, presence  # noqa: E402
from signal_cc.config import Config  # noqa: E402

OWNER = "+15550000001"


class Daemon(BaseHTTPRequestHandler):
    """Records sends; answers each prompt with the next scripted reply(message, timestamp) -> (text, quote).

    In Note to Self mode the reply arrives as a sync of a message sent to the owner, as from the phone;
    a script may return (text, quote, destination) to sync a message sent to someone else.
    """
    sent, params, script, events = [], [], [], queue.Queue()

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
        Daemon.params.append(body["params"])
        ts = 1000 + len(Daemon.sent)
        if Daemon.script and "Timed out" not in message:
            text, quote, *dest = Daemon.script.pop(0)(message, ts)
            msg = {"message": text, **({"quote": {"id": quote}} if quote else {})}
            if body["params"].get("noteToSelf"):
                env = {"syncMessage": {"sentMessage": {"destinationNumber": (dest or [OWNER])[0], **msg}}}
            else:
                env = {"dataMessage": msg}
            Daemon.events.put({"jsonrpc": "2.0", "method": "receive",
                               "params": {"envelope": {"sourceNumber": OWNER, **env}}})
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
        Daemon.params.clear()
        Daemon.script.clear()
        Daemon.events = queue.Queue()
        self.tmp = tempfile.TemporaryDirectory()
        presence.idle_seconds = lambda: 1000  # away from the Mac
        self.cfg = Config(bot="+15550000002", owner=OWNER, home=Path(self.tmp.name),
                          port=self.server.server_port, wait=10)

    def tearDown(self):
        Daemon.events.put(None)  # end the open event stream
        self.tmp.cleanup()

    def test_permission_allowed_by_quoted_reply(self):
        Daemon.script.append(lambda m, ts: ("Y", ts))
        out = hooks.permission(self.cfg, {"tool_name": "Bash", "cwd": "/x/proj",
                                          "tool_input": {"command": "rm -rf build", "description": "Clean"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})
        self.assertIn("rm -rf build", Daemon.sent[0])
        self.assertIn("Bash in proj", Daemon.sent[0])

    def test_own_account_prompts_and_replies_through_note_to_self(self):
        self.cfg = replace(self.cfg, bot="")
        Daemon.script.append(lambda m, ts: ("y", ts))
        out = hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})
        self.assertEqual({k: v for k, v in Daemon.params[0].items() if k != "message"},
                         {"noteToSelf": True, "notifySelf": True})

    def test_own_account_ignores_what_you_send_to_others(self):
        self.cfg = replace(self.cfg, bot="", wait=3)
        Daemon.script.append(lambda m, ts: ("y", ts, "+15550000009"))
        self.assertIsNone(hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        self.assertIn("Timed out", Daemon.sent[-1])

    def test_permission_denied_with_reason_by_tag(self):
        Daemon.script.append(lambda m, ts: (f"{tag(m)} use the test db", None))
        out = hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "psql prod"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"],
                         {"behavior": "deny", "message": "Denied from Signal: use the test db"})

    def other_prompt(self, tag, created):
        self.cfg.pending.mkdir(parents=True, exist_ok=True)
        (self.cfg.pending / tag).write_text(json.dumps(
            {"created": created, "deadline": 9999999999, "summary": "Bash in other:"}))

    def test_plain_reply_while_an_older_prompt_waits_is_left_to_it(self):
        self.other_prompt("0aaa", created=0)
        Daemon.script.append(lambda m, ts: ("y", None))
        self.cfg = replace(self.cfg, wait=3)
        self.assertIsNone(hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        self.assertEqual(len(Daemon.sent), 2)  # the prompt and its timeout; the older prompt owes the hint
        self.assertIn("Timed out", Daemon.sent[-1])

    def test_plain_reply_while_a_newer_prompt_waits_gets_one_hint(self):
        self.other_prompt("0bbb", created=9999999998)
        Daemon.script += [lambda m, ts: ("y", None), lambda m, ts: ("0bbb y", None)]
        self.cfg = replace(self.cfg, wait=3)
        self.assertIsNone(hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        self.assertIn("Which prompt? 2 waiting", Daemon.sent[1])
        self.assertIn("[0bbb] Bash in other:", Daemon.sent[1])
        self.assertIn("Timed out", Daemon.sent[2])  # the reply tagged for the other prompt was not taken

    def test_plain_reply_after_another_message_is_confirmed_first(self):
        def notify_then_reply(m, ts):  # another session's message lands after this prompt
            (self.cfg.home / "last").write_text("")
            return "y", None
        Daemon.script += [notify_then_reply, lambda m, ts: ("y", None)]
        out = hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})
        self.assertIn("Which prompt? 1 waiting", Daemon.sent[1])

    def test_tags_of_waiting_prompts_are_never_reused(self):
        from signal_cc import ask
        drawn = iter(["aaaa", "aaaa", "bbbb"])
        real, ask.secrets.token_hex = ask.secrets.token_hex, lambda n: next(drawn)
        try:
            self.assertEqual([ask.register(self.cfg, "x"), ask.register(self.cfg, "y")], ["aaaa", "bbbb"])
        finally:
            ask.secrets.token_hex = real

    def test_questions_answered_with_numbers_and_free_text(self):
        qs = [{"question": "Which db?", "header": "DB", "multiSelect": False,
               "options": [{"label": "Postgres", "description": "SQL"}, {"label": "Mongo", "description": "Docs"}]},
              {"question": "Which checks?", "header": "Checks", "multiSelect": True,
               "options": [{"label": "lint", "description": ""}, {"label": "tests", "description": ""}]},
              {"question": "Name?", "header": "Name", "multiSelect": False,
               "options": [{"label": "a", "description": ""}, {"label": "b", "description": ""}]}]
        Daemon.script += [lambda m, ts: ("2", ts),  # wrong line count: asked again
                          lambda m, ts: ("2\n1, 2\nmy own name", ts)]
        out = hooks.question(self.cfg, {"tool_input": {"questions": qs}})["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(out["updatedInput"]["questions"], qs)
        self.assertEqual(out["updatedInput"]["answers"],
                         {"Which db?": "Mongo", "Which checks?": "lint, tests", "Name?": "my own name"})
        self.assertIn("Couldn't read", Daemon.sent[1])

    def test_at_the_mac_nothing_is_sent(self):
        presence.idle_seconds = lambda: 5
        self.assertIsNone(hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}}))
        self.assertEqual(Daemon.sent, [])

    def test_without_config_the_hook_prints_nothing(self):
        env = {"SIGNAL_CC_HOME": self.tmp.name, "PATH": "/usr/bin:/bin"}
        run = subprocess.run([sys.executable, str(ROOT / "relay.py"), "permission"], env=env,
                             input='{"tool_name": "Bash", "tool_input": {}}', capture_output=True, text=True)
        self.assertEqual((run.returncode, run.stdout), (0, ""))

    def test_config_rejects_unknown_keys_and_fills_defaults(self):
        path = Path(self.tmp.name) / "config.json"
        os.environ["SIGNAL_CC_HOME"] = self.tmp.name
        try:
            path.write_text('{"bot": "+1", "owner": "+2"}')
            self.assertEqual((Config.load().port, Config.load().wait), (8299, 300))
            path.write_text('{"bot": "+1", "owner": "+2", "wiat": 5}')
            self.assertIsNone(Config.load())
            path.write_text('{"owner": "+2"}')
            self.assertEqual((Config.load().account, Config.load().note_to_self), ("+2", True))
        finally:
            del os.environ["SIGNAL_CC_HOME"]


if __name__ == "__main__":
    unittest.main()
