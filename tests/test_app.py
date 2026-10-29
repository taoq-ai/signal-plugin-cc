"""The use cases against in-memory fakes: no server, no files."""
import threading
import time
import unittest

from support import (Chat, FakeGathering, FakeJournal, FakeMessenger, FakePresence, FakeRegistry, Reply, Waiting,
                     plain, quoting)
from signal_cc.app import conversation, desk
from signal_cc.app.conversation import Conversation, continue_session
from signal_cc.domain import texts
from signal_cc.domain.forms import ContinueForm, PermissionForm, PlanForm, QuestionForm
from signal_cc.domain.model import AT_MAC, CLOSED, Stopped

BASH = PermissionForm("Bash", {"command": "ls"}, "proj")
OTHER = "0fff"


def conv(messenger, registry=None, presence=None, wait=10, journal=None):
    return Conversation(messenger, registry or FakeRegistry(), presence or FakePresence(), wait,
                        journal if journal is not None else FakeJournal(), "s1")


class AskTest(unittest.TestCase):
    def setUp(self):
        conversation.SETTLE, conversation.POLL = 0.3, 0.05

    def test_a_reaction_on_the_prompt_answers_it(self):
        m = FakeMessenger(quoting("\N{THUMBS DOWN SIGN}"))
        self.assertEqual(conv(m).ask(BASH), {"behavior": "deny", "message": "Denied from Signal"})
        self.assertIn("\N{CHECK MARK} Denied from Signal", m.sent[-1])

    def test_a_plain_reply_while_an_older_prompt_waits_is_left_to_it(self):
        m = FakeMessenger(plain("y"))
        self.assertIsNone(conv(m, FakeRegistry(Waiting(0, OTHER, "Bash in other:")), wait=3).ask(BASH))
        self.assertEqual(len(m.sent), 2)  # the prompt and its timeout: the older prompt owes the hint
        self.assertIn(texts.TIMED_OUT, m.sent[-1])

    def test_a_plain_reply_while_a_newer_prompt_waits_gets_one_hint(self):
        other = Waiting(10_000_000_100, OTHER, "Bash in other:")
        m = FakeMessenger(plain("y"), plain(f"{OTHER} y"))  # then a reply tagged for the other prompt
        self.assertIsNone(conv(m, FakeRegistry(other), wait=3).ask(BASH))
        self.assertIn("Which prompt? 2 waiting", m.sent[1])
        self.assertIn(f"[{OTHER}] Bash in other:", m.sent[1])
        self.assertIn(texts.TIMED_OUT, m.sent[2])

    def test_a_plain_reply_after_another_message_is_confirmed_first(self):
        registry = FakeRegistry()

        def another_message_then_y(text, ts):
            registry.mark_latest("")  # another session's message lands after this prompt
            return Reply("y")
        m = FakeMessenger(another_message_then_y, plain("y"))
        self.assertEqual(conv(m, registry).ask(BASH), {"behavior": "allow"})
        self.assertIn("Which prompt? 1 waiting", m.sent[1])

    def test_a_plain_command_is_never_taken_as_an_answer(self):
        m = FakeMessenger(lambda t, ts: None)
        threading.Timer(0.2, lambda: [m.replies.put(Reply("status")), m.replies.put(Reply("y"))]).start()
        self.assertEqual(conv(m).ask(BASH), {"behavior": "allow"})

    def test_questions_by_votes_and_quoted_replies_then_polls_close(self):
        qs = [{"question": "Which db?", "options": [{"label": "Postgres"}, {"label": "Mongo"}]},
              {"question": "Checks?", "multiSelect": True, "options": [{"label": "lint"}, {"label": "tests"}]}]
        vote = lambda *picked: lambda t, ts: Reply("", ts, list(picked))  # noqa: E731
        m = FakeMessenger(lambda t, ts: None, vote(1), vote(1, 0))  # the text, then each poll
        self.assertEqual(conv(m).ask(QuestionForm(qs, "proj")), {"Which db?": "Mongo", "Checks?": "lint, tests"})
        self.assertEqual(m.ended, [1002, 1003])
        self.assertIn("Which db? \N{RIGHTWARDS ARROW} Mongo", m.sent[-1])

    def test_a_plan_goes_with_its_poll_and_a_vote_approves_it(self):
        plan = {"plan": "1. Write hello.txt"}
        m = FakeMessenger(lambda t, ts: None, lambda t, ts: Reply("", ts, [1]))  # the text, then a vote
        decision = conv(m).ask(PlanForm(plan, "proj"))
        self.assertEqual(decision["updatedPermissions"][0]["mode"], "acceptEdits")
        self.assertIn("Plan from proj:\n1. Write hello.txt", m.sent[0])
        self.assertTrue(m.sent[1].startswith("POLL [0001] Approve this plan?"))
        self.assertIn("\N{CHECK MARK} Approved; edits are auto-accepted", m.sent[-1])

    def test_unreadable_replies_are_asked_again(self):
        qs = [{"question": "Which db?", "options": [{"label": "Postgres"}, {"label": "Mongo"}]},
              {"question": "Name?", "options": [{"label": "a"}, {"label": "b"}]}]
        m = FakeMessenger(plain("1\n2\n3"), lambda t, ts: None, lambda t, ts: None, plain("mongo\nB"))
        self.assertEqual(conv(m).ask(QuestionForm(qs, "proj")), {"Which db?": "Mongo", "Name?": "b"})
        self.assertIn(texts.UNREADABLE, m.sent[3])

    def test_refused_polls_fall_back_to_the_text(self):
        m = FakeMessenger(plain("2"))
        m.fail_polls = True
        qs = [{"question": "Which db?", "options": [{"label": "Postgres"}, {"label": "Mongo"}]}]
        self.assertEqual(conv(m).ask(QuestionForm(qs, "proj")), {"Which db?": "Mongo"})
        self.assertEqual(m.ended, [])

    def test_at_the_mac_nothing_is_sent(self):
        m = FakeMessenger()
        for form in (BASH, PlanForm({"plan": "1. Write hello.txt"}, "proj")):
            self.assertIsNone(conv(m, presence=FakePresence(away=False)).ask(form))
        self.assertEqual(m.sent, [])

    def test_coming_back_to_the_mac_hands_the_prompt_back(self):
        m = FakeMessenger()
        self.assertIsNone(conv(m, presence=FakePresence(returned=True)).ask(BASH))
        self.assertIn(texts.BACK_AT_MAC, m.sent[-1])

    def test_the_stream_ending_ends_the_prompt_and_releases_it(self):
        m, registry = FakeMessenger(lambda t, ts: None), FakeRegistry()
        m.replies.put(None)
        self.assertIsNone(conv(m, registry).ask(BASH))
        self.assertEqual(registry.waiting(), [])


class JournalTest(unittest.TestCase):
    def setUp(self):
        conversation.SETTLE, conversation.POLL = 0.3, 0.05

    def ask(self, messenger, presence=None, form=BASH, wait=10):
        journal = FakeJournal()
        conv(messenger, presence=presence, wait=wait, journal=journal).ask(form)
        return journal.lines

    def outcome(self, lines):
        self.assertEqual(len(lines), 1)
        return lines[0]["outcome"]

    def test_an_answered_permission_prompt_is_one_line(self):
        [line] = self.ask(FakeMessenger(quoting("\N{THUMBS UP SIGN}")))
        self.assertEqual({k: line[k] for k in ("kind", "tag", "session", "outcome")},
                         {"kind": "permission", "tag": "0001", "session": "s1", "outcome": "answered"})
        self.assertIsInstance(line["waited"], float)
        self.assertEqual(sorted(line), ["kind", "outcome", "session", "tag", "waited"])

    def test_each_way_a_prompt_ends_is_named(self):
        ended = FakeMessenger(lambda t, ts: None)
        ended.replies.put(None)
        failing = FakeMessenger()
        failing.fail_sends = True
        for messenger, presence, wait, outcome in [
                (FakeMessenger(), None, 0.5, "timed out"),
                (ended, None, 10, "stream ended"),
                (FakeMessenger(), FakePresence(returned=True), 10, "back at the Mac")]:
            with self.subTest(outcome=outcome):
                self.assertEqual(self.outcome(self.ask(messenger, presence, wait=wait)), outcome)
        with self.subTest(outcome="send failed"), self.assertRaises(OSError):
            conv(failing, journal=(journal := FakeJournal())).ask(BASH)
        self.assertEqual(self.outcome(journal.lines), "send failed")

    def test_a_daemon_that_cannot_be_reached_is_an_error_not_a_failed_send(self):
        m, journal = FakeMessenger(), FakeJournal()
        m.subscribe = lambda: (_ for _ in ()).throw(ConnectionRefusedError())
        with self.assertRaises(OSError):
            conv(m, journal=journal).ask(BASH)
        self.assertEqual((journal.lines[0]["outcome"], journal.lines[0]["tag"]), ("error", None))

    def test_a_stream_that_ends_after_the_answer_records_answered(self):
        qs = [{"question": "Checks?", "multiSelect": True, "options": [{"label": "lint"}, {"label": "tests"}]}]
        m = FakeMessenger(lambda t, ts: None)

        def vote_then_end(text, ts):
            m.replies.put(Reply("", ts, [0]))
            m.replies.put(None)  # inside the settle window
        m.script.append(vote_then_end)
        journal = FakeJournal()
        self.assertEqual(conv(m, journal=journal).ask(QuestionForm(qs, "proj")), {"Checks?": "lint"})
        self.assertEqual(self.outcome(journal.lines), "answered")

    def test_a_prompt_ended_by_sigterm_is_quieted_not_an_error(self):
        m, journal = FakeMessenger(), FakeJournal()
        m.replies.get = lambda timeout: (_ for _ in ()).throw(SystemExit(0))  # what exit_on_sigterm raises
        with self.assertRaises(SystemExit):
            continue_session(conv(m, journal=journal), ContinueForm("Done.", "proj"), grace=5, wait=10)
        self.assertEqual(self.outcome(journal.lines), "quieted")

    def test_an_error_while_waiting_is_recorded_and_raised(self):
        registry, journal = FakeRegistry(), FakeJournal()
        registry.waiting = lambda: 1 / 0
        m = FakeMessenger(plain("y"))
        with self.assertRaises(ZeroDivisionError):
            conv(m, registry, journal=journal).ask(BASH)
        self.assertEqual(self.outcome(journal.lines), "error")

    def test_questions_and_continues_name_their_kind(self):
        qs = [{"question": "Which db?", "options": [{"label": "Postgres"}, {"label": "Mongo"}]}]
        [line] = self.ask(FakeMessenger(plain("2")), form=QuestionForm(qs, "proj"))
        self.assertEqual((line["kind"], line["outcome"]), ("question", "answered"))
        journal = FakeJournal()
        continue_session(conv(FakeMessenger(quoting("go on")), journal=journal), ContinueForm("Done.", "proj"),
                         grace=5, wait=10)
        self.assertEqual((journal.lines[0]["kind"], journal.lines[0]["outcome"]), ("continue", "answered"))

    def test_nothing_is_recorded_while_the_owner_is_at_the_mac(self):
        self.assertEqual(self.ask(FakeMessenger(), FakePresence(away=False)), [])


class ContinueTest(unittest.TestCase):
    def setUp(self):
        conversation.POLL = 0.05

    def test_sends_the_last_message_once_away_and_returns_the_reply(self):
        m = FakeMessenger(quoting("run the tests too"))
        reply = continue_session(conv(m), ContinueForm("Done.", "proj"), grace=5, wait=10)
        self.assertEqual(reply, "run the tests too")
        self.assertIn("proj:\nDone.", m.sent[0])
        self.assertIn("\N{CHECK MARK} Sent to proj", m.sent[-1])

    def test_the_claim_lasts_as_long_as_the_session_listens(self):
        m, registry, seen = FakeMessenger(lambda t, ts: None), FakeRegistry(), []

        def check_then_reply():
            seen.extend(w.tag for w in registry.waiting())
            m.replies.put(Reply("go on", 1001))
        threading.Timer(0.8, check_then_reply).start()  # past the prompt wait of 0.3 s, inside the listen wait
        c = conv(m, registry, wait=0.3)
        self.assertEqual(continue_session(c, ContinueForm("Done.", "proj"), grace=5, wait=5), "go on")
        self.assertEqual(seen, ["0001"])

    def test_stays_silent_when_the_owner_stays_at_the_mac(self):
        m = FakeMessenger()
        c = conv(m, presence=FakePresence(away=False))
        self.assertIsNone(continue_session(c, ContinueForm("Done.", "proj"), grace=0.2, wait=10))
        self.assertEqual(m.sent, [])


class StoppedTest(unittest.TestCase):
    """hooks.quiet stops a waiting listener; the listener tells Signal when the Mac took over."""

    def setUp(self):
        conversation.SETTLE, conversation.POLL = 0.3, 0.05

    def stop_while_waiting(self, why):
        m, registry, journal = FakeMessenger(), FakeRegistry(), FakeJournal()
        m.replies.get = lambda timeout: (_ for _ in ()).throw(Stopped(why))  # what processes raises
        with self.assertRaises(SystemExit) as stopped:
            continue_session(conv(m, registry, journal=journal), ContinueForm("Done.", "proj"), grace=5, wait=10)
        self.assertEqual(stopped.exception.code, 0)  # exits quietly: the session is not woken
        self.assertEqual(registry.waiting(), [])
        return m.sent[1:], journal.lines

    def test_a_prompt_typed_at_the_mac_sends_one_tagged_notice(self):
        sent, [line] = self.stop_while_waiting(AT_MAC)
        self.assertEqual(sent, [f"[0001] {texts.STOPPED[AT_MAC]}"])
        self.assertEqual(line["outcome"], "answered at the Mac")

    def test_a_closed_session_says_so(self):
        sent, [line] = self.stop_while_waiting(CLOSED)
        self.assertEqual(sent, [f"[0001] {texts.STOPPED[CLOSED]}"])
        self.assertIn("closed", texts.STOPPED[CLOSED])
        self.assertEqual(line["outcome"], "session closed")

    def test_a_listener_replaced_by_a_new_turn_sends_nothing(self):
        sent, [line] = self.stop_while_waiting(None)
        self.assertEqual((sent, line["outcome"]), ([], "quieted"))

    def test_a_prompt_already_answered_or_timed_out_gets_no_notice(self):
        for name, script, wait in [("answered", (quoting("go on"),), 10), ("timed out", (), 0.3)]:
            with self.subTest(outcome=name):
                m, journal = FakeMessenger(*script), FakeJournal()
                send = m.send

                def stop_on_the_last_word(text):  # the receipt or timeout went out; then quiet() lands
                    ts = send(text)
                    if texts.CHECK in text or texts.TIMED_OUT in text:
                        raise Stopped(AT_MAC)
                    return ts
                m.send = stop_on_the_last_word
                with self.assertRaises(SystemExit):
                    continue_session(conv(m, journal=journal), ContinueForm("Done.", "proj"), grace=5, wait=wait)
                self.assertEqual(len(m.sent), 2)
                self.assertNotIn(texts.STOPPED[AT_MAC], m.sent[-1])
                self.assertEqual(journal.lines[0]["outcome"], name)

    def test_a_notice_that_cannot_be_sent_still_ends_quietly(self):
        for error in (OSError("connection refused"), RuntimeError("daemon refused")):  # signal_cli raises both
            with self.subTest(error=type(error).__name__):
                m, journal = FakeMessenger(), FakeJournal()

                def stop_then_fail(timeout):
                    m.send = lambda text: (_ for _ in ()).throw(error)
                    raise Stopped(AT_MAC)
                m.replies.get = stop_then_fail
                with self.assertRaises(SystemExit) as stopped:
                    continue_session(conv(m, journal=journal), ContinueForm("Done.", "proj"), grace=5, wait=10)
                self.assertEqual(stopped.exception.code, 0)
                self.assertEqual(journal.lines[0]["outcome"], "answered at the Mac")


class Ear:
    """One listener's side of a shared chat, which hooks.quiet can stop like it stops a listener process."""

    def __init__(self, chat):
        self.chat, self.stop = chat, None

    def send(self, text):
        return self.chat.send(text)

    def send_poll(self, question, options, multi):
        return self.chat.send_poll(question, options, multi)

    def end_poll(self, ts):
        self.chat.end_poll(ts)

    def subscribe(self):
        replies, close = self.chat.subscribe()
        get = replies.get

        def stoppable(timeout=None):
            if self.stop:
                raise Stopped(self.stop)
            return get(timeout=timeout)
        replies.get = stoppable
        return replies, close


class DigestTest(unittest.TestCase):
    """Several sessions finished while the owner was at the Mac: one digest when they leave."""

    def setUp(self):
        conversation.POLL, conversation.GATHER, conversation.STEP = 0.05, 0.3, 0.02
        self.chat, self.registry, self.gathering = Chat(), FakeRegistry(), FakeGathering()
        self.journal, self.results, self.threads, self.ears = FakeJournal(), {}, [], {}
        self.addCleanup(self.end)

    def finish(self, project, last="Done."):
        """A session's turn ends and its listener starts; the owner is away."""
        ear = self.ears[project] = Ear(self.chat)
        c = Conversation(ear, self.registry, FakePresence(), 10, self.journal, project, self.gathering)

        def run():
            try:
                self.results[project] = continue_session(c, ContinueForm(last, project), grace=5, wait=10)
            except SystemExit as stopped:
                self.results[project] = stopped
        thread = threading.Thread(target=run)
        thread.start()
        self.threads.append(thread)

    def until(self, check, what):
        end = time.time() + 5
        while not check():
            if time.time() > end:
                self.fail(f"waited for {what}; sent {self.chat.sent}")
            time.sleep(0.02)

    def sent_count(self, n):
        self.until(lambda: len(self.chat.sent) >= n, f"{n} messages")
        time.sleep(0.2)  # and nothing more
        self.assertEqual(len(self.chat.sent), n, self.chat.sent)

    def ts(self, i):
        return 1001 + i  # FakeMessenger stamps each message in turn

    def tag(self, project):
        return {w.summary: w.tag for w in self.registry.waiting()}[f"{project}:"]

    def end(self):
        self.chat.post(None)
        for thread in self.threads:
            thread.join(5)

    def three(self):
        for project in ("a", "b", "c"):
            self.finish(project, f"{project} is done.\nDetails follow.")
        self.sent_count(2)  # the digest and its poll
        return [self.tag(p) for p in ("a", "b", "c")]

    def test_three_finished_sessions_get_one_digest_and_a_tag_wakes_one(self):
        a, b, c = self.three()
        self.assertEqual(self.chat.sent[0], f"3 sessions finished:\n[{a}] a: a is done.\N{HORIZONTAL ELLIPSIS}\n"
                                            f"[{b}] b: b is done.\N{HORIZONTAL ELLIPSIS}\n[{c}] c: c is done.\N{HORIZONTAL ELLIPSIS}\n\n"
                                            "Start a reply with a tag to continue that session, "
                                            "or pick one in the poll to read it in full.")
        self.assertEqual(self.chat.sent[1], f"POLL Which session? ['[{a}] a', '[{b}] b', '[{c}] c'] multi=False")
        self.chat.post(Reply(f"[{a}] run the tests too"))
        self.until(lambda: "a" in self.results, "a to wake")
        self.assertEqual(self.results["a"], "run the tests too")
        self.sent_count(3)
        self.assertEqual(self.chat.sent[2], f"[{a}] \N{CHECK MARK} Sent to a")
        self.assertNotIn("b", self.results)
        self.end()
        self.assertEqual((self.results["b"], self.results["c"]), (None, None))
        self.assertEqual(sorted((line["session"], line.get("digest")) for line in self.journal.lines),
                         [("a", 3), ("b", 3), ("c", 3)])
        self.assertIn(self.ts(1), self.chat.ended)  # the last member to end closes the poll

    def test_a_reply_quoting_or_reacting_to_the_digest_gets_one_hint(self):
        a, b, c = self.three()
        self.chat.post(Reply("sounds good", self.ts(0)))
        self.sent_count(3)
        self.assertTrue(self.chat.sent[2].startswith("Which prompt? 3 waiting:"), self.chat.sent[2])
        self.chat.post(Reply("\N{THUMBS UP SIGN}", self.ts(1)))
        self.sent_count(4)
        self.assertTrue(self.chat.sent[3].startswith("Which prompt? 3 waiting:"))
        self.assertEqual(self.results, {})

    def test_a_poll_pick_shows_that_session_in_full_and_a_quote_of_it_wakes_it(self):
        a, b, c = self.three()
        self.chat.post(Reply("", self.ts(1), [1]))
        self.sent_count(3)
        self.assertEqual(self.chat.sent[2], f"[{b}] b:\nb is done.\nDetails follow.\n\nReply to continue this session.")
        self.assertEqual(self.results, {})
        self.chat.post(Reply("go on"))  # plain, three waiting: still the hint
        self.sent_count(4)
        self.assertTrue(self.chat.sent[3].startswith("Which prompt? 3 waiting:"))
        self.chat.post(Reply("go on", self.ts(2)))
        self.until(lambda: "b" in self.results, "b to wake")
        self.assertEqual(self.results, {"b": "go on"})

    def test_one_finished_session_gets_todays_single_message(self):
        self.finish("a")
        self.sent_count(1)
        self.assertEqual(self.chat.sent[0], f"[{self.tag('a')}] a:\nDone.\n\nReply to continue this session.")
        self.chat.post(Reply("go on"))
        self.until(lambda: "a" in self.results, "a to wake")
        self.assertEqual(self.results["a"], "go on")
        self.assertNotIn("digest", self.journal.lines[0])

    def test_a_session_already_on_signal_is_listed_with_a_pointer_and_its_message_still_works(self):
        self.finish("e")
        self.sent_count(1)  # sent alone, before the others finished
        e = self.tag("e")
        self.finish("a")
        self.finish("b")
        self.sent_count(3)
        a, b = self.tag("a"), self.tag("b")
        self.assertIn(f"3 sessions finished:\n[{e}] e: (sent at ", self.chat.sent[1])
        self.assertIn(f", above)\n[{a}] a: Done.\n[{b}] b: Done.\n", self.chat.sent[1])
        self.assertEqual(self.chat.sent[2], f"POLL Which session? ['[{a}] a', '[{b}] b'] multi=False")
        self.chat.post(Reply("go on", self.ts(0)))  # quotes e's own message
        self.until(lambda: "e" in self.results, "e to wake")
        self.assertEqual(self.results, {"e": "go on"})

    def test_a_session_taken_over_at_the_mac_no_longer_takes_replies_from_the_digest(self):
        a, b, c = self.three()
        self.ears["a"].stop = AT_MAC
        self.chat.post(Reply("", 1))  # wakes the listeners' waits; quotes nothing of theirs
        self.sent_count(3)
        self.assertEqual(self.chat.sent[2], f"[{a}] {texts.STOPPED[AT_MAC]}")
        self.chat.post(Reply(f"[{a}] go on"))
        self.sent_count(4)
        self.assertEqual(self.chat.sent[3], f"[{a}] {texts.GONE}")
        self.assertEqual(list(self.results), ["a"])
        self.assertEqual(self.results["a"].code, 0)

    def test_more_than_ten_sessions_are_all_listed_and_the_poll_holds_ten(self):
        projects = [f"p{i:02}" for i in range(11)]
        for project in projects:
            self.finish(project)
        self.sent_count(2)
        self.assertTrue(self.chat.sent[0].startswith("11 sessions finished:"))
        self.assertEqual(self.chat.sent[0].count("Done."), 11)
        self.assertEqual(self.chat.sent[1].count("', '") + 1, 10)  # signal-cli takes 2 to 10 options
        last = sorted(projects, key=self.tag)[-1]
        self.chat.post(Reply(f"{self.tag(last)} go on"))  # not in the poll: its tag still reaches it
        self.until(lambda: last in self.results, "the eleventh to wake")
        self.assertEqual(self.results, {last: "go on"})

    def test_a_refused_poll_leaves_the_digest_and_its_tags(self):
        self.chat.fail_polls = True
        for project in ("a", "b"):
            self.finish(project)
        self.sent_count(1)
        self.assertTrue(self.chat.sent[0].startswith("2 sessions finished:"))
        self.chat.post(Reply(f"{self.tag('b')} go on"))
        self.until(lambda: "b" in self.results, "b to wake")
        self.assertEqual(self.results, {"b": "go on"})


class DeskTest(unittest.TestCase):
    def test_answers_status_and_nothing_else(self):
        m, registry = FakeMessenger(), FakeRegistry(Waiting(0, OTHER, "Bash in other:"))
        for reply in (Reply("Status"), Reply("y"), Reply("status", 1001), None):
            m.replies.put(reply)
        desk.serve(m, registry, FakePresence())
        self.assertEqual(len(m.sent), 1)
        self.assertIn(f"Waiting for you (1):\n[{OTHER}] Bash in other:", m.sent[0])
        self.assertEqual(registry.latest(), OTHER)  # a plain reply to the status is for that prompt

    def test_away_and_back_flip_the_switch_and_status_shows_it(self):
        m, registry, presence = FakeMessenger(), FakeRegistry(Waiting(0, OTHER, "Bash in other:")), FakePresence()
        seen = []
        registry.mark_latest(OTHER)
        m.send = lambda text: seen.append((text, presence.switch_on(), registry.latest())) or 1
        for reply in (Reply("away"), Reply("status"), Reply("away", 1001), Reply("Back"), Reply("status"), None):
            m.replies.put(reply)
        desk.serve(m, registry, presence)
        self.assertEqual([(t.splitlines()[-1], on) for t, on, _ in seen],
                         [(texts.AWAY_ON, True), (texts.AWAY_ON, True), (texts.AWAY_OFF, False),
                          (texts.AWAY_OFF, False)])  # the quoted away is an answer, not a command
        self.assertEqual(seen[0][2], "")  # a plain reply to the confirmation is for no prompt


if __name__ == "__main__":
    unittest.main()
