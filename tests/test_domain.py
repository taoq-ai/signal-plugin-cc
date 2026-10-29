"""The rules, with no I/O."""
import unittest

from support import Reply, Waiting
from signal_cc.domain import texts
from signal_cc.domain.forms import ContinueForm, PermissionForm, QuestionForm, decide, pick
from signal_cc.domain.model import PARTIAL
from signal_cc.domain.routing import HINT, SKIP, Take, route

ME, OTHER = "0a01", "0b02"
SENT = {101: None, 102: 0}  # my text message, and my poll 0
OLD, NEW = Waiting(1, OTHER, "Bash in other:"), Waiting(9, OTHER, "Bash in other:")
MINE = Waiting(5, ME, "Bash in proj:")


class RoutingTest(unittest.TestCase):
    def test_a_reply_never_crosses_to_another_prompt(self):
        cases = [  # reply, waiting prompts, latest tag -> where it goes
            (Reply("y"), [MINE], ME, Take(Reply("y"), None)),  # plain, only me, my message is the latest
            (Reply("y"), [MINE], "", HINT),  # plain, but another message came after mine
            (Reply("y"), [OLD, MINE], ME, SKIP),  # plain, an older prompt waits: it owes the hint
            (Reply("y"), [MINE, NEW], ME, HINT),  # plain, I am the oldest: I say which prompt?
            (Reply(f"{ME} y"), [OLD, MINE], OTHER, Take(Reply("y"), None)),  # tagged for me
            (Reply(f"[{OTHER}] n"), [MINE, NEW], ME, SKIP),  # tagged for the other
            (Reply("y", 102), [OLD, MINE], OTHER, Take(Reply("y", 102), 0)),  # quotes my poll
            (Reply("y", 999), [MINE], ME, SKIP),  # quotes someone else's message
            (Reply("\N{THUMBS UP SIGN}", 101), [MINE], ME, Take(Reply("\N{THUMBS UP SIGN}", 101), None)),
            (Reply("", 102, [1]), [MINE], ME, Take(Reply("", 102, [1]), 0)),  # a vote in my poll
            (Reply("status"), [MINE], ME, SKIP),  # a command is for the desk
            (Reply("status", 101), [MINE], ME, Take(Reply("status", 101), None)),  # quoted: an answer
        ]
        for reply, live, latest, want in cases:
            with self.subTest(reply=reply, live=[w.tag for w in live], latest=latest):
                self.assertEqual(route(reply, ME, SENT, live, latest), want)


class FormsTest(unittest.TestCase):
    def test_decide(self):
        for text in ("y", "Yes", "\N{THUMBS UP SIGN}", "\N{THUMBS UP SIGN}\U0001F3FD", "\N{THUMBS UP SIGN}️"):
            self.assertEqual(decide(text), {"behavior": "allow"}, text)
        self.assertEqual(decide("\N{THUMBS DOWN SIGN}\U0001F3FF"), {"behavior": "deny", "message": "Denied from Signal"})
        self.assertEqual(decide("use the test db")["message"], "Denied from Signal: use the test db")

    def test_pick(self):
        q = {"options": [{"label": "Postgres"}, {"label": "Mongo"}], "multiSelect": False}
        self.assertEqual([pick(q, "2"), pick(q, "mongo"), pick(q, "1,2"), pick(q, "my own")],
                         ["Mongo", "Mongo", "1,2", "my own"])  # several numbers only for multi-select
        self.assertEqual(pick({**q, "multiSelect": True}, "2, 1"), "Mongo, Postgres")

    def test_question_form_takes_answers_in_any_order(self):
        qs = [{"question": "Which db?", "options": [{"label": "Postgres"}, {"label": "Mongo"}]},
              {"question": "Checks?", "multiSelect": True, "options": [{"label": "lint"}, {"label": "tests"}]},
              {"question": "Name?", "options": [{"label": "a"}, {"label": "b"}]}]
        form = QuestionForm(qs, "proj")
        self.assertEqual([p.multi for p in form.polls], [False, True, False])
        self.assertEqual(form.polls[1].question, "(2/3) Checks?")
        self.assertIs(form.parse(Reply("", 2, [1, 0]), 1), PARTIAL)  # ticks, in any order
        self.assertIsNone(form.parse(Reply("1\n2\n3"), None))  # more lines than open questions
        self.assertIs(form.parse(Reply("mongo"), None), PARTIAL)  # fills the first open question
        self.assertEqual(form.parse(Reply("my own name", 3), 2),
                         {"Which db?": "Mongo", "Checks?": "lint, tests", "Name?": "my own name"})

    def test_texts(self):
        self.assertIn("rm -rf build", PermissionForm("Bash", {"command": "rm -rf build"}, "proj").text)
        self.assertTrue(ContinueForm("x" * 2000, "proj").text.endswith("\N{HORIZONTAL ELLIPSIS}\n\nReply to continue "
                                                                       "this session."))
        self.assertEqual(texts.status([], 0), ("Nothing is waiting for you.", ""))
        text, tag = texts.status([MINE], 5 + 180)
        self.assertEqual((text, tag), (f"Waiting for you (1):\n[{ME}] Bash in proj: \N{MIDDLE DOT} 3 min ago", ME))
        self.assertEqual(texts.hint([MINE, NEW])[1], "")  # several waiting: a plain reply counts for none


if __name__ == "__main__":
    unittest.main()
