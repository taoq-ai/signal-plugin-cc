"""The use cases against in-memory fakes: no server, no files."""
import threading
import unittest

from support import FakeMessenger, FakePresence, FakeRegistry, Reply, Waiting, plain, quoting
from signal_cc.app import conversation, desk
from signal_cc.app.conversation import Conversation, continue_session
from signal_cc.domain import texts
from signal_cc.domain.forms import ContinueForm, PermissionForm, QuestionForm

BASH = PermissionForm("Bash", {"command": "ls"}, "proj")
OTHER = "0fff"


def conv(messenger, registry=None, presence=None, wait=10):
    return Conversation(messenger, registry or FakeRegistry(), presence or FakePresence(), wait)


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
        self.assertIsNone(conv(m, presence=FakePresence(away=False)).ask(BASH))
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


class DeskTest(unittest.TestCase):
    def test_answers_status_and_nothing_else(self):
        m, registry = FakeMessenger(), FakeRegistry(Waiting(0, OTHER, "Bash in other:"))
        for reply in (Reply("Status"), Reply("y"), Reply("status", 1001), None):
            m.replies.put(reply)
        desk.serve(m, registry)
        self.assertEqual(len(m.sent), 1)
        self.assertIn(f"Waiting for you (1):\n[{OTHER}] Bash in other:", m.sent[0])
        self.assertEqual(registry.latest(), OTHER)  # a plain reply to the status is for that prompt


if __name__ == "__main__":
    unittest.main()
