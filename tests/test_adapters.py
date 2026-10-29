"""The adapters, and the hooks end to end, against a stub signal-cli daemon and real files."""
import contextlib
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from unittest import mock
from pathlib import Path

from support import OWNER, ROOT, Reply, StubDaemon, serve
from signal_cc.adapters import files, macos, private, processes, signal_cli
from signal_cc.adapters.files import AwaySwitch, DeskLock, FileJournal, FileRegistry, Listeners
from signal_cc.adapters.signal_cli import SignalCli
from signal_cc.app import conversation
from signal_cc.config import Config
from signal_cc.entry import cli, hooks


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
        env = mock.patch.dict(os.environ)  # the run the tests run in must not decide whether a session is headless
        env.start()
        self.addCleanup(env.stop)
        for key in ("CLAUDE_PID", "CLAUDE_CODE_ENTRYPOINT"):
            os.environ.pop(key, None)

    def claude(self, *args):
        """A stand-in for the Claude Code process, with its arguments, named by CLAUDE_PID as in a hook."""
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", *args])
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        os.environ["CLAUDE_PID"] = str(proc.pid)
        return proc

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

    def test_the_journal_appends_one_timed_json_line_per_entry(self):
        journal = FileJournal(self.home / "new")  # the home may not exist yet
        journal.record({"kind": "permission", "outcome": "answered"})
        journal.record({"handler": "listen", "outcome": "error", "error": "OSError"})
        lines = [json.loads(line) for line in (self.home / "new" / "relay.log").read_text().splitlines()]
        self.assertEqual([{k: v for k, v in line.items() if k != "time"} for line in lines],
                         [{"kind": "permission", "outcome": "answered"},
                          {"handler": "listen", "outcome": "error", "error": "OSError"}])
        self.assertRegex(lines[0]["time"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_a_journal_that_cannot_write_never_breaks_the_relay(self):
        (self.home / "relay.log").mkdir()  # not a writable file
        with contextlib.redirect_stderr(err := io.StringIO()):
            FileJournal(self.home).record({"outcome": "answered"})
        self.assertIn("relay.log", err.getvalue())

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


class HeadlessTest(Base):
    def test_print_mode_is_headless_even_with_an_inherited_entrypoint(self):
        for args in [("-p", "reply ok"), ("--print", "x")]:
            with self.subTest(args=args):
                self.claude(*args)
                os.environ["CLAUDE_CODE_ENTRYPOINT"] = "claude-desktop"  # inherited from the desktop session
                self.assertTrue(processes.headless())

    def test_only_a_single_pid_is_read(self):
        printing = self.claude("-p", "reply ok")
        os.environ["CLAUDE_PID"] = f"1,{printing.pid}"  # ps would read both processes
        os.environ["CLAUDE_CODE_ENTRYPOINT"] = "cli"
        self.assertFalse(processes.headless())

    def test_without_ps_the_entrypoint_decides(self):
        self.claude("-p", "reply ok")
        os.environ["PATH"] = ""
        for entrypoint, expected in [("sdk-cli", True), ("cli", False)]:
            with self.subTest(entrypoint=entrypoint):
                os.environ["CLAUDE_CODE_ENTRYPOINT"] = entrypoint
                self.assertEqual(processes.headless(), expected)

    def test_interactive_and_streaming_sessions_are_not(self):
        for args, entrypoint in [((), "cli"), (("--output-format", "stream-json", "--input-format", "stream-json"),
                                               "claude-desktop"),
                                 (("--print", "--input-format", "stream-json"), "sdk-cli"),
                                 (("--print", "--input-format=stream-json"), "sdk-cli")]:
            with self.subTest(args=args):
                self.claude(*args)
                os.environ["CLAUDE_CODE_ENTRYPOINT"] = entrypoint
                self.assertFalse(processes.headless())

    def test_without_the_claude_process_the_entrypoint_decides(self):
        os.environ["CLAUDE_PID"] = "999999999"  # gone
        for entrypoint, expected in [("sdk-cli", True), ("cli", False), (None, False)]:
            with self.subTest(entrypoint=entrypoint):
                os.environ.pop("CLAUDE_CODE_ENTRYPOINT", None)
                if entrypoint:
                    os.environ["CLAUDE_CODE_ENTRYPOINT"] = entrypoint
                self.assertEqual(processes.headless(), expected)


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

    def test_plan_feedback_end_to_end(self):
        plan = {"plan": "1. Write hello.txt", "planFilePath": "/p/plan.md"}
        self.answer_next_send(lambda ts: {"sourceNumber": OWNER, "dataMessage": {"message": "add a migration step",
                                                                                 "quote": {"id": ts}}})
        out = hooks.permission(self.cfg, {"tool_name": "ExitPlanMode", "cwd": "/x/proj", "tool_input": plan})
        self.assertEqual(out["hookSpecificOutput"], {"hookEventName": "PermissionRequest", "decision": {
            "behavior": "deny", "message": "Keep planning. The owner replied from Signal: add a migration step"}})
        self.assertIn("Plan from proj", StubDaemon.calls[0][1]["message"])
        self.assertEqual(StubDaemon.calls[1][0], "sendPollCreate")

    def test_a_plan_is_approved_with_its_input(self):
        plan = {"plan": "1. Write hello.txt", "planFilePath": "/p/plan.md"}
        self.answer_next_send(lambda ts: {"sourceNumber": OWNER, "dataMessage": {
            "reaction": {"emoji": "\N{THUMBS UP SIGN}", "targetSentTimestamp": ts}}})
        out = hooks.permission(self.cfg, {"tool_name": "ExitPlanMode", "cwd": "/x/proj", "tool_input": plan})
        self.assertEqual(out["hookSpecificOutput"]["decision"], {"behavior": "allow", "updatedInput": plan})
        [line] = [json.loads(row) for row in (self.home / "relay.log").read_text().splitlines()]
        self.assertEqual((line["kind"], line["outcome"]), ("plan", "answered"))

    def test_ask_user_question_is_left_to_the_question_hook(self):
        qs = {"questions": [{"question": "Which db?", "options": [{"label": "Postgres"}, {"label": "Mongo"}]}]}
        self.assertIsNone(hooks.permission(self.cfg, {"tool_name": "AskUserQuestion", "cwd": "/x/proj",
                                                      "tool_input": qs}))
        self.assertEqual(StubDaemon.calls, [])

    def test_the_log_holds_the_outcome_but_no_message_text_or_number(self):
        self.answer_next_send(lambda ts: {"sourceNumber": OWNER, "dataMessage": {
            "message": "\N{THUMBS UP SIGN}", "quote": {"id": ts}}})
        hooks.permission(self.cfg, {"tool_name": "Bash", "cwd": "/x/proj", "session_id": "s9",
                                    "tool_input": {"command": "echo hush-7f3a", "description": "say hush"}})
        self.assertIn("hush-7f3a", StubDaemon.calls[0][1]["message"])  # it was sent
        log = (self.home / "relay.log").read_text()
        [line] = [json.loads(row) for row in log.splitlines()]
        self.assertEqual((line["kind"], line["session"], line["outcome"]), ("permission", "s9", "answered"))
        for secret in ("hush", "proj", "Bash", OWNER, OWNER.lstrip("+"), self.cfg.bot.lstrip("+")):
            self.assertNotIn(secret, log)

    def test_listen_wakes_the_session_with_the_reply(self):
        self.answer_next_send(lambda ts: {"sourceNumber": OWNER,
                                          "dataMessage": {"message": "run the tests too", "quote": {"id": ts}}})
        err = io.StringIO()
        with self.assertRaises(SystemExit) as woke, contextlib.redirect_stderr(err):
            hooks.listen(self.cfg, {"session_id": "s1", "cwd": "/x/proj", "last_assistant_message": "Done."})
        self.assertEqual(woke.exception.code, 2)
        self.assertIn("run the tests too", err.getvalue())
        self.assertIsNone(Listeners(self.home).get("s1"))

    def test_listen_in_a_headless_run_returns_at_once(self):
        self.claude("-p", "reply ok")
        os.environ["CLAUDE_CODE_ENTRYPOINT"] = "sdk-cli"
        self.cfg = replace(self.cfg, wait=1, listen=1)  # without the guard, stop waiting soon
        began = time.monotonic()
        out = hooks.listen(self.cfg, {"session_id": "s1", "cwd": "/x/proj", "last_assistant_message": "Done.",
                                      "stop_hook_active": False})
        self.assertLess(time.monotonic() - began, 1)
        self.assertEqual((out, StubDaemon.calls, Listeners(self.home).get("s1")), (None, [], None))

    def test_a_listener_quieted_mid_wait_is_logged_as_quieted(self):
        """UserPromptSubmit and SessionEnd stop a waiting listener with SIGTERM: a normal end, not an error."""
        before = signal.getsignal(signal.SIGTERM)
        threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
        try:
            with self.assertRaises(SystemExit):
                hooks.listen(self.cfg, {"session_id": "s1", "cwd": "/x/proj", "last_assistant_message": "Done."})
        finally:
            signal.signal(signal.SIGTERM, before)
        [line] = [json.loads(row) for row in (self.home / "relay.log").read_text().splitlines()]
        self.assertEqual((line["kind"], line["session"], line["outcome"]), ("continue", "s1", "quieted"))

    def test_a_listener_stopped_by_a_prompt_at_the_mac_tells_signal(self):
        sigs = (signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2)  # listen installs a handler for each
        before = {sig: signal.getsignal(sig) for sig in sigs}
        threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGUSR1)).start()  # what quiet sends it
        try:
            with self.assertRaises(SystemExit) as stopped:
                hooks.listen(self.cfg, {"session_id": "s1", "cwd": "/x/proj", "last_assistant_message": "Done."})
        finally:
            for sig, handler in before.items():
                signal.signal(sig, handler)
        self.assertEqual(stopped.exception.code, 0)
        sends = [params["message"] for method, params in StubDaemon.calls if method == "send"]
        self.assertEqual(len(sends), 2)
        tag = sends[0][1:5]
        self.assertTrue(sends[1].startswith(f"[{tag}] Answered at the Mac"))
        [line] = [json.loads(row) for row in (self.home / "relay.log").read_text().splitlines()]
        self.assertEqual((line["tag"], line["outcome"]), (tag, "answered at the Mac"))

    def test_quiet_tells_the_listener_why_it_stops(self):
        catch = ("import signal, sys, time\n"
                 "for s in (signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2):\n"
                 "    signal.signal(s, lambda n, f: (print(n, flush=True), sys.exit()))\n"
                 "print('ready', flush=True)\ntime.sleep(30)")
        cases = [({"hook_event_name": "UserPromptSubmit", "prompt": "run it"}, signal.SIGUSR1),
                 ({"hook_event_name": "SessionEnd"}, signal.SIGUSR2),
                 ({"hook_event_name": "UserPromptSubmit", "prompt": f"{hooks.WOKEN}\ngo on"}, signal.SIGTERM),
                 ({"hook_event_name": "Stop"}, signal.SIGTERM)]
        for hook, expected in cases:
            with self.subTest(hook=hook["hook_event_name"], expected=expected.name):
                fake = subprocess.Popen([sys.executable, "-c", catch, "relay.py"], stdout=subprocess.PIPE, text=True)
                try:
                    self.assertEqual(fake.stdout.readline().strip(), "ready")
                    Listeners(self.home).set("s1", fake.pid)
                    hooks.quiet(self.cfg, {**hook, "session_id": "s1"})
                    self.assertEqual(int(fake.stdout.readline()), expected)
                finally:
                    fake.kill()
                    fake.wait()
                    fake.stdout.close()

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


class PrivateHomeTest(Base):
    """Other local accounts can't read the relay's state, and a planted symlink never redirects a write."""

    def setUp(self):
        super().setUp()
        old = os.umask(0o022)  # the usual default, under which plain files come out 0644
        self.addCleanup(os.umask, old)

    def write_everything(self, home):
        """Every write the relay makes under its home, with no process started."""
        cfg = replace(self.cfg, home=home)
        self.answer_next_send(lambda ts: {"sourceNumber": OWNER, "dataMessage": {"message": "Y", "quote": {"id": ts}}})
        hooks.permission(cfg, {"tool_name": "Bash", "cwd": "/x/proj", "tool_input": {"command": "ls"}})
        FileRegistry(home).claim("waiting", 60)
        FileRegistry(home).mark_latest("abcd")
        AwaySwitch(home).set(True)
        Listeners(home).set("s1", 123)
        lock = DeskLock(home)
        lock.acquire()
        lock.release()
        with mock.patch.object(processes.subprocess, "Popen"), mock.patch.object(signal_cli.subprocess, "Popen"):
            processes.spawn("desk", home / "daemon.log")
            SignalCli(cfg).start()

    def test_a_fresh_home_is_0700_and_every_file_in_it_0600(self):
        home = self.home / "fresh"
        self.write_everything(home)
        modes = {str(p.relative_to(home)): stat.S_IMODE(p.stat().st_mode) for p in home.rglob("*")}
        self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)
        self.assertEqual({p for p in modes}, {"relay.log", "pending", "pending/" + next(home.glob("pending/*")).name,
                                              "last", "away", "listeners", "listeners/s1.pid", "desk.lock",
                                              "daemon.log"})
        self.assertEqual({p: m for p, m in modes.items() if m != (0o700 if (home / p).is_dir() else 0o600)}, {})

    def test_an_existing_home_left_open_is_tightened(self):
        home = self.home / "open"
        home.mkdir(mode=0o755)
        FileJournal(home).record({"outcome": "answered"})
        self.assertEqual(stat.S_IMODE(home.stat().st_mode), 0o700)

    def test_no_write_follows_a_symlink_planted_in_the_home(self):
        home, outside = self.home / "home", self.home / "outside"
        home.mkdir(mode=0o700)
        outside.mkdir()
        for name in ("relay.log", "last", "away", "desk.lock", "daemon.log"):
            (outside / name).write_text("kept")
            (home / name).symlink_to(outside / name)
        (outside / "pending").mkdir()
        (home / "pending").symlink_to(outside / "pending")
        (outside / "listeners").mkdir()
        (outside / "listeners" / "s1.pid").write_text("kept")
        (home / "listeners").mkdir(mode=0o700)
        (home / "listeners" / "s1.pid").symlink_to(outside / "listeners" / "s1.pid")
        with contextlib.redirect_stderr(err := io.StringIO()):
            FileJournal(home).record({"outcome": "answered"})
        self.assertIn("relay.log", err.getvalue())
        writes = [lambda: FileRegistry(home).claim("waiting", 60), lambda: FileRegistry(home).mark_latest("abcd"),
                  lambda: AwaySwitch(home).set(True), lambda: Listeners(home).set("s1", 123),
                  lambda: DeskLock(home).acquire(), lambda: processes.spawn("desk", home / "daemon.log"),
                  lambda: SignalCli(replace(self.cfg, home=home)).start()]
        with mock.patch.object(processes.subprocess, "Popen") as spawned, \
                mock.patch.object(signal_cli.subprocess, "Popen") as started:
            for i, write in enumerate(writes):
                with self.subTest(write=i), self.assertRaises(OSError):
                    write()
        self.assertEqual((spawned.called, started.called), (False, False))
        self.assertEqual({str(p.relative_to(outside)): p.read_text() for p in outside.rglob("*") if p.is_file()},
                         {name: "kept" for name in ("relay.log", "last", "away", "desk.lock", "daemon.log",
                                                    "listeners/s1.pid")})

    def test_a_symlinked_listeners_folder_is_not_written_through(self):
        home, outside = self.home / "home", self.home / "outside"
        home.mkdir(mode=0o700)
        outside.mkdir()
        (home / "listeners").symlink_to(outside)
        with self.assertRaises(OSError):
            Listeners(home).set("s1", 123)
        self.assertEqual(list(outside.iterdir()), [])

    def test_the_daemon_log_alone_creates_a_private_home(self):
        with mock.patch.object(processes.subprocess, "Popen"), mock.patch.object(signal_cli.subprocess, "Popen"):
            processes.spawn("desk", self.home / "a" / "daemon.log")
            SignalCli(replace(self.cfg, home=self.home / "b")).start()
        self.assertEqual([stat.S_IMODE((self.home / h).stat().st_mode) for h in "ab"], [0o700, 0o700])

    def test_a_shorter_pid_or_tag_replaces_a_longer_one_whole(self):
        listeners, registry = Listeners(self.home), FileRegistry(self.home)
        listeners.set("s", 12345)
        listeners.set("s", 7)
        registry.mark_latest("abcdef")
        registry.mark_latest("ab")
        self.assertEqual((listeners.get("s"), registry.latest()), (7, "ab"))

    def test_sessions_appending_at_once_keep_every_line(self):
        path = self.home / "relay.log"
        with private.open_file(path, "a") as first, private.open_file(path, "a") as second:  # both open, then write
            first.write("one\n")
            first.flush()
            second.write("two\n")
        self.assertEqual(path.read_text(), "one\ntwo\n")

    def test_a_prompt_logged_through_a_planted_symlink_leaves_the_target_and_the_hook_quiet(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
            target = Path(elsewhere, "target")
            target.write_text("kept")
            Path(tmp, "relay.log").symlink_to(target)
            Path(tmp, "config.json").write_text(json.dumps(
                {"owner": OWNER, "port": 1, "signal_cli": str(Path(tmp, "no-signal-cli"))}))
            run = subprocess.run([sys.executable, str(ROOT / "relay.py"), "start"],
                                 env={"SIGNAL_CC_HOME": tmp, "PATH": "/usr/bin:/bin"},
                                 input="{}", capture_output=True, text=True)
            self.assertEqual((run.returncode, run.stdout, target.read_text()), (0, "", "kept"))
            self.assertIn("relay.log", run.stderr)


class PathGuardTest(Base):
    """A session id never leaves the home, a home another account owns is never used, and quiet never
    deletes through a symlinked listeners/ folder. Each refusal is one stderr line, an exit 0, no output."""

    def setUp(self):
        super().setUp()
        self.home = self.home / "home"
        self.outside = Path(self.tmp.name) / "outside"
        self.home.mkdir(mode=0o700)
        self.outside.mkdir()
        (self.home / "config.json").write_text(json.dumps({"owner": OWNER, "port": self.server.server_port,
                                                                   "wait": 1, "listen": 1}))  # bounded if a guard fails
        os.environ["SIGNAL_CC_HOME"] = str(self.home)

    def run_hook(self, handler, hook):
        """cli.main in process, as relay.py runs it: (stdout, stderr lines)."""
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(hook))), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err), mock.patch.object(processes, "headless", return_value=False), \
                mock.patch.object(processes.subprocess, "Popen") as spawned, \
                mock.patch.object(signal_cli.subprocess, "Popen") as started:
            cli.main(["relay.py", handler])
        self.assertEqual((spawned.called, started.called), (False, False))
        return out.getvalue(), err.getvalue().splitlines()

    def tree(self, root):
        return {str(p.relative_to(root)): (p.is_symlink() or p.is_dir() or p.read_text())
                for p in root.rglob("*")}

    def test_a_session_id_that_is_not_a_plain_token_is_refused(self):
        for good in ("s1", "unknown", "0b6f2c1e-6a1d-4c1e-9f2a-3d4e5f6a7b8c", "a_B-9"):
            self.assertEqual(hooks.session_id({"session_id": good}), good)
        self.assertEqual(hooks.session_id({}), "unknown")
        for bad in ("", ".", "..", "a/b", "a.b", "s1\n", "../../escape", "/abs", "\u00e9", 7, None):
            with self.subTest(bad=bad), self.assertRaises(hooks.Refused):
                hooks.session_id({"session_id": bad})

    def test_listen_and_quiet_never_touch_a_file_outside_the_home(self):
        (self.outside / "kept.pid").write_text("kept")
        (self.home.parent / "escape.pid").write_text("kept")  # what home/listeners/../../escape.pid names
        before = self.tree(Path(self.tmp.name))
        for handler in ("listen", "quiet"):
            for session in ("../../escape", str(self.outside / "kept"), str(self.outside / "new")):
                with self.subTest(handler=handler, session=session):
                    out, err = self.run_hook(handler, {"session_id": session, "hook_event_name": "SessionEnd",
                                                       "cwd": "/x/proj", "last_assistant_message": "Done."})
                    self.assertEqual((out, len(err)), ("", 1))
                    self.assertIn("session_id", err[0])
                    after = self.tree(Path(self.tmp.name))
                    self.assertEqual({k: v for k, v in after.items() if k != "home/relay.log"}, before)
        self.assertEqual(StubDaemon.calls, [])
        errors = {json.loads(line)["error"] for line in (self.home / "relay.log").read_text().splitlines()}
        self.assertEqual(errors, {"Refused"})  # the journal, in the home, records the type only

    def foreign(self):
        """The home's stat as if another account owned it (Path.stat: 3.9's pathlib binds os.stat early)."""
        real, home = Path.stat, self.home

        def stat(path, *args, **kwargs):
            st = real(path, *args, **kwargs)
            if path == home:
                st = os.stat_result((*st[:4], st.st_uid + 1, *st[5:10]))
            return st
        return mock.patch.object(Path, "stat", stat)

    def test_a_home_another_account_owns_is_refused_by_every_hook(self):
        os.chmod(self.home, 0o755)
        (self.home / "away").write_text("")
        (self.home / "listeners").mkdir()
        (self.home / "listeners" / "s1.pid").write_text("1")
        before = self.tree(self.home)
        for handler in ("start", "permission", "question", "listen", "quiet", "desk"):
            StubDaemon.events.put(None)  # if the guard fails, the desk's event stream ends at once
            with self.subTest(handler=handler), self.foreign():
                out, err = self.run_hook(handler, {"session_id": "s1", "hook_event_name": "UserPromptSubmit",
                                                   "prompt": "hi", "tool_name": "Bash", "tool_input": {}})
                self.assertEqual((out, len(err)), ("", 1))
                self.assertIn("another account", err[0])
                self.assertEqual(self.tree(self.home), before)
                self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o755)  # not tightened either
        self.assertEqual(StubDaemon.calls, [])

    def test_private_home_refuses_a_foreign_owner(self):
        with self.foreign(), self.assertRaises(PermissionError):
            private.home(self.home)

    def test_quiet_never_deletes_through_a_symlinked_listeners_folder(self):
        (self.outside / "s1.pid").write_text("kept")
        (self.home / "listeners").symlink_to(self.outside)
        out, err = self.run_hook("quiet", {"session_id": "s1", "hook_event_name": "SessionEnd"})
        self.assertEqual((out, len(err), (self.outside / "s1.pid").read_text()), ("", 1, "kept"))
        with self.assertRaises(OSError):
            Listeners(self.home).clear("s1")
        self.assertEqual((self.outside / "s1.pid").read_text(), "kept")

    def test_clear_still_removes_a_real_pid_file_and_a_missing_one_is_fine(self):
        listeners = Listeners(self.home)
        listeners.clear("s1")  # no listeners/ yet
        listeners.set("s1", 123)
        listeners.clear("s1", 999)  # another listener's: kept
        self.assertEqual(listeners.get("s1"), 123)
        listeners.clear("s1")
        listeners.clear("s1")
        self.assertIsNone(listeners.get("s1"))


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

    def test_without_fcntl_every_hook_exits_silently(self):
        # Windows has no fcntl; the relay must not fail at import there, even when set up
        run_without_fcntl = ("import runpy, sys; sys.modules['fcntl'] = None; sys.argv[0] = %r; "
                             "runpy.run_path(sys.argv[0], run_name='__main__')" % str(ROOT / "relay.py"))
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "config.json").write_text('{"owner": "+2", "port": 1}')
            for handler in ("start", "permission", "question", "listen", "quiet", "desk"):
                with self.subTest(handler=handler):
                    run = subprocess.run([sys.executable, "-c", run_without_fcntl, handler],
                                         env={"SIGNAL_CC_HOME": tmp, "PATH": "/usr/bin:/bin"},
                                         input='{"tool_name": "Bash", "tool_input": {}}', capture_output=True,
                                         text=True, timeout=10)
                    self.assertEqual((run.returncode, run.stdout, run.stderr), (0, "", ""))

    def test_a_failing_handler_is_logged_and_the_hook_still_exits_quietly(self):
        # port 1 is closed and signal_cli is missing, so start fails with an OSError and no daemon is touched
        cases = [("permission", '{"tool_name": "Bash", "tool_input": {"command": "echo hush"', "JSONDecodeError"),
                 ("start", "{}", "FileNotFoundError"),
                 ("bogus-hush", "{}", "KeyError")]
        for handler, stdin, error in cases:
            with self.subTest(handler=handler), tempfile.TemporaryDirectory() as tmp:
                Path(tmp, "config.json").write_text(json.dumps(
                    {"owner": OWNER, "port": 1, "signal_cli": str(Path(tmp, "no-signal-cli"))}))
                run = subprocess.run([sys.executable, str(ROOT / "relay.py"), handler],
                                     env={"SIGNAL_CC_HOME": tmp, "PATH": "/usr/bin:/bin"},
                                     input=stdin, capture_output=True, text=True)
                log = Path(tmp, "relay.log").read_text()
                self.assertEqual((run.returncode, run.stdout), (0, ""))
                line = json.loads(log)
                self.assertEqual({k: v for k, v in line.items() if k != "time"},
                                 {"handler": handler if handler in ("permission", "start") else "unknown",
                                  "outcome": "error", "error": error})
                self.assertNotIn("hush", log)

    def test_the_relay_is_the_entry_processes_spawn(self):
        self.assertEqual(processes.RELAY, ROOT / "relay.py")


if __name__ == "__main__":
    unittest.main()
