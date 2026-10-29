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
from signal_cc.adapters.files import AwaySwitch, DeskLock, FileRegistry, Listeners
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
            with self.assertRaises(subprocess.TimeoutExpired):  # still alive after a SIGTERM would have landed
                other.wait(timeout=2)
            self.assertIsNone(listeners.get("s1"))
        finally:
            for p in (fake, other):
                p.kill()
                p.wait()


class PresenceTest(Base):
    def test_the_switch_overrides_idle_time_and_unknown_idle_means_at_the_mac(self):
        presence = macos.MacPresence(60, AwaySwitch(self.home))
        cases = [  # idle seconds, switch -> away, returned
            (5, False, False, True), (1000, False, True, False), (None, False, False, False),
            (5, True, True, False), (None, True, True, False)]
        for idle, on, away, returned in cases:
            with self.subTest(idle=idle, switch=on):
                macos.idle_seconds = lambda: idle
                presence.set_switch(on)
                self.assertEqual((presence.away(), presence.returned(), presence.switch_on()), (away, returned, on))

    def test_the_switch_is_shared_through_the_config_home(self):
        AwaySwitch(self.home / "new").set(True)
        self.assertTrue(AwaySwitch(self.home / "new").on())
        AwaySwitch(self.home / "new").set(False)
        AwaySwitch(self.home / "new").set(False)  # already off
        self.assertFalse(AwaySwitch(self.home / "new").on())


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

    def test_away_from_signal_sends_the_next_prompt_there_though_the_mac_is_in_use(self):
        macos.idle_seconds = lambda: 5
        runner = threading.Thread(target=hooks.run_desk, args=(self.cfg,))
        runner.start()
        time.sleep(0.5)
        StubDaemon.push({"sourceNumber": OWNER, "dataMessage": {"message": "away"}})
        time.sleep(0.3)
        StubDaemon.events.put(None)
        runner.join(timeout=5)
        self.assertIn("Away switch on", StubDaemon.calls[0][1]["message"])
        StubDaemon.reset()
        self.answer_next_send(lambda ts: {"sourceNumber": OWNER, "dataMessage": {"message": "y", "quote": {"id": ts}}})
        out = hooks.permission(self.cfg, {"tool_name": "Bash", "cwd": "/x/proj", "tool_input": {"command": "ls"}})
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow"})

    def test_a_prompt_typed_at_the_mac_turns_the_switch_off_and_session_end_does_not(self):
        switch = AwaySwitch(self.home)
        switch.set(True)
        hooks.quiet(self.cfg, {"hook_event_name": "SessionEnd", "session_id": "s1"})
        self.assertTrue(switch.on())
        hooks.quiet(self.cfg, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "run it"})
        self.assertFalse(switch.on())

    def test_a_turn_woken_from_signal_leaves_the_switch_on(self):
        switch = AwaySwitch(self.home)
        switch.set(True)
        self.answer_next_send(lambda ts: {"sourceNumber": OWNER,
                                          "dataMessage": {"message": "go on", "quote": {"id": ts}}})
        err = io.StringIO()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(err):
            hooks.listen(self.cfg, {"session_id": "s1", "cwd": "/x/proj", "last_assistant_message": "Done."})
        wake = f"<task-notification>Stop hook feedback:\n{err.getvalue()}</task-notification>"
        hooks.quiet(self.cfg, {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": wake})
        self.assertTrue(switch.on())


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
