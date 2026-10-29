"""The adapters, and the hooks end to end, against a stub signal-cli daemon and real files."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

from support import OWNER, ROOT, Reply, StubDaemon, serve
from signal_cc.adapters import files, macos, processes
from signal_cc.adapters.files import DeskLock, FileRegistry, Listeners
from signal_cc.adapters.signal_cli import SignalCli
from signal_cc.app import conversation
from signal_cc.config import Config
from signal_cc.entry import hooks


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = serve()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        StubDaemon.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        macos.idle_seconds = lambda: 1000  # away from the Mac
        conversation.SETTLE, conversation.POLL = 0.3, 0.05
        self.cfg = Config(owner=OWNER, bot="+15550000002", home=self.home, port=self.server.server_port, wait=10)

    def tearDown(self):
        StubDaemon.events.put(None)  # end any open event stream
        self.tmp.cleanup()

    def answer_next_send(self, envelope_for):
        """When the relay sends its next message, push envelope_for(timestamp) as the owner's reply."""
        def watch():
            for _ in range(200):
                sends = [c for c in StubDaemon.calls if c[0] == "send"]
                if sends:
                    StubDaemon.push(envelope_for(1000 + StubDaemon.calls.index(sends[0]) + 1))
                    return
                time.sleep(0.02)
        threading.Thread(target=watch, daemon=True).start()


class SignalCliTest(Base):
    def test_bot_mode_messages_the_owner(self):
        SignalCli(self.cfg).send("hi")
        self.assertEqual(StubDaemon.calls, [("send", {"recipient": [OWNER], "message": "hi"})])

    def test_own_account_uses_note_to_self_and_notifies(self):
        SignalCli(replace(self.cfg, bot="")).send("hi")
        self.assertEqual(StubDaemon.calls, [("send", {"noteToSelf": True, "notifySelf": True, "message": "hi"})])

    def test_a_refused_poll_raises(self):
        StubDaemon.fail_polls = True
        with self.assertRaisesRegex(RuntimeError, "poll too long"):
            SignalCli(self.cfg).send_poll("q", ["a"], False)

    def test_events_become_replies_from_the_owner_only(self):
        cli = SignalCli(replace(self.cfg, bot=""))
        replies, close = cli.subscribe()
        sync = lambda msg, to=OWNER: {"sourceNumber": OWNER,  # noqa: E731
                                       "syncMessage": {"sentMessage": {"destinationNumber": to, **msg}}}
        for env in [sync({"message": "y", "quote": {"id": 7}}),
                    sync({"reaction": {"emoji": "\N{THUMBS UP SIGN}", "targetSentTimestamp": 8}}),
                    sync({"pollVote": {"targetSentTimestamp": 9, "optionIndexes": [1]}}),
                    sync({"pollVote": {"targetSentTimestamp": 9, "optionIndexes": []}}),  # withdrawn
                    sync({"message": "hi"}, to="+15550000009"),  # you, writing to someone else
                    {"sourceNumber": "+15550000009", "dataMessage": {"message": "hi"}}]:  # someone else
            StubDaemon.push(env)
        StubDaemon.events.put(None)
        got = []
        while (reply := replies.get(timeout=5)) is not None:
            got.append(reply)
        close()
        self.assertEqual(got, [Reply("y", 7), Reply("\N{THUMBS UP SIGN}", 8), Reply("", 9, [1])])


class FilesTest(Base):
    def test_claims_never_reuse_a_waiting_tag_and_expire(self):
        registry, drawn = FileRegistry(self.home), iter(["aaaa", "aaaa", "bbbb", "cccc"])
        real, files.secrets.token_hex = files.secrets.token_hex, lambda n: next(drawn)
        try:
            self.assertEqual([registry.claim("x", 60), registry.claim("y", 60)], ["aaaa", "bbbb"])
            registry.claim("z", -1)  # already expired
        finally:
            files.secrets.token_hex = real
        self.assertEqual([w.tag for w in registry.waiting()], ["aaaa", "bbbb"])
        registry.release("aaaa")
        registry.mark_latest("bbbb")
        self.assertEqual(([w.tag for w in registry.waiting()], registry.latest()), (["bbbb"], "bbbb"))

    def test_one_desk_lock_at_a_time(self):
        first, second = DeskLock(self.home), DeskLock(self.home)
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()

    def test_stop_ends_a_relay_process_and_nothing_else(self):
        fake = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "relay.py"])
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            listeners = Listeners(self.home)
            listeners.set("s1", fake.pid)
            listeners.set("s2", other.pid)
            hooks.quiet(self.cfg, {"session_id": "s1"})
            hooks.quiet(self.cfg, {"session_id": "s2"})  # not a relay process: left alone
            self.assertIsNotNone(fake.wait(timeout=5))
            self.assertIsNone(other.poll())
            self.assertIsNone(listeners.get("s1"))
        finally:
            for p in (fake, other):
                p.kill()
                p.wait()


class HooksTest(Base):
    def test_permission_end_to_end(self):
        self.answer_next_send(lambda ts: {"sourceNumber": OWNER, "dataMessage": {"message": "Y", "quote": {"id": ts}}})
        out = hooks.permission(self.cfg, {"tool_name": "Bash", "cwd": "/x/proj", "tool_input": {"command": "ls"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})
        self.assertIn("Bash in proj", StubDaemon.calls[0][1]["message"])

    def test_listen_wakes_the_session_with_the_reply(self):
        self.answer_next_send(lambda ts: {"sourceNumber": OWNER,
                                          "dataMessage": {"message": "run the tests too", "quote": {"id": ts}}})
        err = io.StringIO()
        with self.assertRaises(SystemExit) as woke, contextlib.redirect_stderr(err):
            hooks.listen(self.cfg, {"session_id": "s1", "cwd": "/x/proj", "last_assistant_message": "Done."})
        self.assertEqual(woke.exception.code, 2)
        self.assertIn("run the tests too", err.getvalue())
        self.assertIsNone(Listeners(self.home).get("s1"))

    def test_the_desk_answers_status(self):
        registry = FileRegistry(self.home)
        registry.claim("Bash in other:", 60)
        runner = threading.Thread(target=hooks.run_desk, args=(self.cfg,))
        runner.start()
        time.sleep(0.5)
        StubDaemon.push({"sourceNumber": OWNER, "dataMessage": {"message": "status"}})
        time.sleep(0.3)
        StubDaemon.events.put(None)  # the daemon goes away: the desk stops
        runner.join(timeout=5)
        self.assertFalse(runner.is_alive())
        self.assertIn("Waiting for you (1)", StubDaemon.calls[0][1]["message"])


class ConfigTest(unittest.TestCase):
    def test_unknown_keys_turn_the_plugin_off_and_defaults_fill_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            os.environ["SIGNAL_CC_HOME"] = tmp
            try:
                path.write_text('{"owner": "+2"}')
                cfg = Config.load()
                self.assertEqual((cfg.port, cfg.wait, cfg.account, cfg.note_to_self), (8299, 300, "+2", True))
                path.write_text('{"owner": "+2", "wiat": 5}')
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertIsNone(Config.load())
            finally:
                del os.environ["SIGNAL_CC_HOME"]

    def test_without_config_the_hook_prints_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = subprocess.run([sys.executable, str(ROOT / "relay.py"), "permission"],
                                 env={"SIGNAL_CC_HOME": tmp, "PATH": "/usr/bin:/bin"},
                                 input='{"tool_name": "Bash", "tool_input": {}}', capture_output=True, text=True)
        self.assertEqual((run.returncode, run.stdout, run.stderr), (0, "", ""))

    def test_the_relay_is_the_entry_processes_spawn(self):
        self.assertEqual(processes.RELAY, ROOT / "relay.py")


if __name__ == "__main__":
    unittest.main()
