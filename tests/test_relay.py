"""End-to-end checks of relay.py against a stub signal-cli HTTP daemon. Run: python3 -m unittest discover -s tests"""
import contextlib
import io
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from signal_cc import ask, hooks, presence  # noqa: E402
from signal_cc.config import Config  # noqa: E402

OWNER = "+15550000001"


class Daemon(BaseHTTPRequestHandler):
    """Records sends; answers each prompt with the next scripted reply(message, timestamp) -> (text, quote).

    In Note to Self mode the reply arrives as a sync of a message sent to the owner, as from the phone;
    a script may return (text, quote, destination) to sync a message sent to someone else, a dict as
    text to send that message body (a vote, a reaction), or None to stay silent. Polls count as sends
    (their question as the message); receipts and timeouts never get a reply.
    """
    sent, params, script, events, ended, fail_polls = [], [], [], queue.Queue(), [], False

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
        method, params = body["method"], body["params"]
        if method == "sendPollTerminate":
            Daemon.ended.append(params["pollTimestamp"])
            return self.answer(body, {})
        if method == "sendPollCreate" and Daemon.fail_polls:
            return self.answer(body, None, {"code": -1, "message": "poll too long"})
        message = params.get("message") or params["question"]
        Daemon.sent.append(message)
        Daemon.params.append(params)
        ts = 1000 + len(Daemon.sent)
        scripted = Daemon.script.pop(0)(message, ts) \
            if Daemon.script and "Timed out" not in message and "\N{CHECK MARK}" not in message else None
        if scripted:
            text, quote, *dest = scripted
            msg = text if isinstance(text, dict) else {"message": text, **({"quote": {"id": quote}} if quote else {})}
            if body["params"].get("noteToSelf"):
                env = {"syncMessage": {"sentMessage": {"destinationNumber": (dest or [OWNER])[0], **msg}}}
            else:
                env = {"dataMessage": msg}
            Daemon.events.put({"jsonrpc": "2.0", "method": "receive",
                               "params": {"envelope": {"sourceNumber": OWNER, **env}}})
        self.answer(body, {"timestamp": ts})

    def answer(self, body, result, error=None):
        reply = {"jsonrpc": "2.0", "id": body["id"], **({"error": error} if error else {"result": result})}
        out = json.dumps(reply).encode()
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
        Daemon.ended.clear()
        Daemon.fail_polls = False
        ask.SETTLE = 0.3
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

    def test_reactions_answer_the_message_they_react_to(self):
        def react(emoji, target):
            return {"reaction": {"emoji": emoji, "targetSentTimestamp": target, "isRemove": False}}, None
        Daemon.script.append(lambda m, ts: react("\N{THUMBS DOWN SIGN}", ts))
        out = hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "deny", "message": "Denied from Signal"})
        Daemon.script.append(lambda m, ts: react("\N{THUMBS UP SIGN}", ts - 1))  # another message's reaction
        self.cfg = replace(self.cfg, wait=3)
        self.assertIsNone(hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}}))

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

    def test_questions_answered_by_votes_and_quoted_replies_in_any_order(self):
        qs = [{"question": "Which db?", "header": "DB", "multiSelect": False,
               "options": [{"label": "Postgres", "description": "SQL"}, {"label": "Mongo", "description": "Docs"}]},
              {"question": "Which checks?", "header": "Checks", "multiSelect": True,
               "options": [{"label": "lint", "description": ""}, {"label": "tests", "description": ""}]},
              {"question": "Name?", "header": "Name", "multiSelect": False,
               "options": [{"label": "a", "description": ""}, {"label": "b", "description": ""}]}]

        def vote(*picked):
            return lambda m, ts: ({"pollVote": {"targetSentTimestamp": ts, "optionIndexes": list(picked)}}, None)
        Daemon.script += [lambda m, ts: None,  # the text message: no reply
                          vote(1), vote(1, 0),  # tap poll 1, tick two boxes in poll 2 (in either order)
                          lambda m, ts: ("my own name", ts)]  # quote poll 3 with a free answer
        out = hooks.question(self.cfg, {"cwd": "/x/proj", "tool_input": {"questions": qs}})["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "allow")
        self.assertEqual(out["updatedInput"]["questions"], qs)
        self.assertEqual(out["updatedInput"]["answers"],
                         {"Which db?": "Mongo", "Which checks?": "lint, tests", "Name?": "my own name"})
        self.assertEqual([p.get("noMulti") for p in Daemon.params[1:4]], [True, False, True])
        self.assertIn("(2/3) Which checks?", Daemon.sent[2])
        self.assertEqual(sorted(Daemon.ended), [1002, 1003, 1004])  # every poll closed
        self.assertIn("\N{CHECK MARK} Which db? \N{RIGHTWARDS ARROW} Mongo", Daemon.sent[-1])

    def test_questions_answered_by_lines_and_labels(self):
        qs = [{"question": "Which db?", "options": [{"label": "Postgres"}, {"label": "Mongo"}]},
              {"question": "Name?", "options": [{"label": "a"}, {"label": "b"}]}]
        Daemon.script += [lambda m, ts: ("1\n2\n3", None),  # more lines than questions: asked again
                          lambda m, ts: None, lambda m, ts: None,  # the polls
                          lambda m, ts: ("mongo\nB", None)]  # labels, in any case
        out = hooks.question(self.cfg, {"tool_input": {"questions": qs}})["hookSpecificOutput"]
        self.assertEqual(out["updatedInput"]["answers"], {"Which db?": "Mongo", "Name?": "b"})
        self.assertIn("Couldn't read", Daemon.sent[3])

    def test_questions_fall_back_to_text_when_polls_fail(self):
        Daemon.fail_polls = True
        qs = [{"question": "Which db?", "options": [{"label": "Postgres"}, {"label": "Mongo"}]}]
        Daemon.script.append(lambda m, ts: ("2", None))
        out = hooks.question(self.cfg, {"tool_input": {"questions": qs}})["hookSpecificOutput"]
        self.assertEqual(out["updatedInput"]["answers"], {"Which db?": "Mongo"})
        self.assertEqual(Daemon.ended, [])

    def test_listen_sends_the_last_message_and_wakes_the_session_with_the_reply(self):
        Daemon.script.append(lambda m, ts: ("run the tests too", ts))
        err = io.StringIO()
        with self.assertRaises(SystemExit) as woke, contextlib.redirect_stderr(err):
            hooks.listen(self.cfg, {"session_id": "s1", "cwd": "/x/proj",
                                    "last_assistant_message": "Refactor done; 7 tests pass."})
        self.assertEqual(woke.exception.code, 2)
        self.assertIn("run the tests too", err.getvalue())
        self.assertIn("proj:\nRefactor done; 7 tests pass.", Daemon.sent[0])
        self.assertIn("\N{CHECK MARK} Sent to proj", Daemon.sent[-1])
        self.assertFalse((self.cfg.home / "listeners" / "s1.pid").exists())

    def test_listen_stays_silent_when_the_owner_stays_at_the_mac(self):
        presence.idle_seconds = lambda: 0
        real, hooks.time.sleep = hooks.time.sleep, lambda s: real(0.05)
        try:
            self.assertIsNone(hooks.listen(replace(self.cfg, wait=0.2), {"session_id": "s2"}))
        finally:
            hooks.time.sleep = real
        self.assertEqual(Daemon.sent, [])

    def test_quiet_stops_the_session_listener_and_nothing_else(self):
        fake = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "relay.py"])
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            pids = self.cfg.home / "listeners"
            pids.mkdir(parents=True)
            (pids / "s3.pid").write_text(str(fake.pid))
            (pids / "s4.pid").write_text(str(other.pid))
            hooks.quiet(self.cfg, {"session_id": "s3"})
            hooks.quiet(self.cfg, {"session_id": "s4"})  # not a relay process: left alone
            self.assertIsNotNone(fake.wait(timeout=5))
            self.assertIsNone(other.poll())
        finally:
            fake.kill()
            other.kill()

    def incoming(self, text):
        Daemon.events.put({"jsonrpc": "2.0", "method": "receive",
                           "params": {"envelope": {"sourceNumber": OWNER, "dataMessage": {"message": text}}}})

    def test_desk_answers_status_with_what_is_waiting(self):
        from signal_cc import desk
        self.other_prompt("0aaa", created=0)
        self.other_prompt("0bbb", created=1)
        runner = threading.Thread(target=desk.run, args=(self.cfg,))
        runner.start()
        time.sleep(0.5)  # the first desk takes the lock
        self.assertFalse(desk.run(self.cfg))  # a second desk exits at once
        self.incoming("Status")
        self.incoming("y")  # not a command: ignored
        time.sleep(0.3)
        Daemon.events.put(None)  # the daemon goes away: the desk stops
        runner.join(timeout=5)
        self.assertFalse(runner.is_alive())
        self.assertEqual(len(Daemon.sent), 1)
        self.assertIn("Waiting for you (2):\n[0aaa] Bash in other:", Daemon.sent[0])

    def test_a_plain_command_is_never_taken_as_an_answer(self):
        def status_then_yes(m, ts):
            self.incoming("status")
            return "y", None
        Daemon.script.append(status_then_yes)
        out = hooks.permission(self.cfg, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})

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
