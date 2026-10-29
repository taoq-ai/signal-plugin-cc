"""The rules, with no I/O."""
import unittest

from support import Reply, Waiting
from signal_cc.domain import texts
from signal_cc.domain.forms import ContinueForm, PermissionForm, PlanForm, QuestionForm, decide, pick
from signal_cc.domain.model import PARTIAL, Digest
from signal_cc.domain.routing import HINT, SHOW, SKIP, Gone, Take, route

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
            (Reply(" Away "), [MINE], ME, SKIP),  # the away switch is for the desk too
            (Reply("back"), [MINE], ME, SKIP),
            (Reply("away", 101), [MINE], ME, Take(Reply("away", 101), None)),  # quoted: an answer
        ]
        for reply, live, latest, want in cases:
            with self.subTest(reply=reply, live=[w.tag for w in live], latest=latest):
                self.assertEqual(route(reply, ME, SENT, live, latest), want)

    def test_a_reply_to_a_digest_reaches_one_session_or_none(self):
        third = "0c03"
        first = Waiting(1, OTHER, "other:")  # the oldest member: it owes the hint
        later = Waiting(7, third, "third:")
        # the digest text (201) and its poll (202), shared by the three members; 101 is my own full message
        sent = {101: None, 201: Digest((OTHER, ME, third), None), 202: Digest((OTHER, ME, third), (OTHER, ME, third))}
        all3 = [first, MINE, later]
        cases = [  # reply, waiting prompts, who I am -> where it goes
            (Reply(f"[{ME}] run the tests too", 201), all3, ME, Take(Reply("run the tests too", 201), None)),
            (Reply(f"[{OTHER}] run the tests too"), all3, ME, SKIP),  # tagged for another member
            (Reply("sounds good", 201), all3, ME, SKIP),  # quotes the digest: the oldest member says which
            (Reply("sounds good", 201), all3, OTHER, HINT),
            (Reply("👍", 201), all3, OTHER, HINT),  # a reaction names no session either
            (Reply("👍", 202), all3, OTHER, HINT),
            (Reply("👍", 202), all3, ME, SKIP),
            (Reply("", 202, [1]), all3, ME, SHOW),  # picked me in the poll: show my full message
            (Reply("", 202, [1]), all3, OTHER, SKIP),
            (Reply("", 202, [7]), all3, ME, SKIP),  # no such option
            (Reply("go on", 101), all3, ME, Take(Reply("go on", 101), None)),  # quotes my full message
            (Reply("go on"), all3, ME, SKIP),  # plain, several waiting: the oldest says which
            (Reply("go on"), all3, OTHER, HINT),
            (Reply("sounds good", 201), [MINE, later], ME, HINT),  # the oldest member left: I am the oldest now
            (Reply(f"[{OTHER}] go on"), [MINE, later], ME, Gone(OTHER)),  # taken over at the Mac
            (Reply(f"[{OTHER}] go on"), [MINE, later], third, SKIP),
            (Reply(f"[{OTHER}] go on"), [MINE, later], "0d04", SKIP),  # not in the digest: knows nothing of it
            (Reply(f"[{third}] go on"), [MINE], ME, SKIP),  # this reply just woke third: not gone, no hint either
            (Reply("", 202, [0]), [MINE, later], ME, Gone(OTHER)),  # picked a member taken over at the Mac
            (Reply("", 202, [0]), [MINE, later], third, SKIP),
            (Reply("", 202, [-1]), all3, third, SKIP),  # no such option, from either end
            (Reply("", 202, [0, 1]), all3, ME, SKIP),  # a single-choice poll: two picks name no one
            (Reply(f"[{OTHER}] go on"), [Waiting(0, "0d04", "Bash in x:"), MINE], "0d04", SKIP),  # older, not in it
        ]
        for reply, live, me, want in cases:
            with self.subTest(reply=reply, me=me, live=[w.tag for w in live]):
                mine = sent if me != "0d04" else {}
                self.assertEqual(route(reply, me, mine, live, "", gone={OTHER}), want)


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

    def test_plan_form_reads_votes_reactions_and_feedback(self):
        plan = {"plan": "# Plan\n1. Write hello.txt", "planFilePath": "/p/plan.md"}
        form = PlanForm(plan, "proj")
        self.assertIn("Plan from proj:\n# Plan\n1. Write hello.txt", form.text)
        self.assertEqual(len(form.polls), 1)
        self.assertEqual(len(form.polls[0].options), 3)
        self.assertFalse(form.polls[0].multi)
        ask = {"behavior": "allow", "updatedInput": plan}  # updatedInput: an allow without it leaves plan mode on
        auto = {**ask, "updatedPermissions": [{"type": "setMode", "mode": "acceptEdits", "destination": "session"}]}
        keep = {"behavior": "deny", "message": "Keep planning (from Signal)"}
        cases = [
            (Reply("", 102, [0]), 0, ask),
            (Reply("", 102, [1]), 0, auto),
            (Reply("", 102, [2]), 0, keep),
            (Reply("\N{THUMBS UP SIGN}\U0001F3FD", 101), None, ask),
            (Reply("\N{THUMBS DOWN SIGN}", 101), None, keep),
            (Reply("n"), None, keep),
            (Reply("add a migration step", 101), None,
             {"behavior": "deny", "message": "Keep planning. The owner replied from Signal: add a migration step"}),
            (Reply("add a migration step", 102), 0,
             {"behavior": "deny", "message": "Keep planning. The owner replied from Signal: add a migration step"}),
            (Reply(""), None, None),
            (Reply("", 102, []), 0, None),
            (Reply("", 102, [3]), 0, None),
        ]
        for reply, target, want in cases:
            with self.subTest(reply=reply):
                self.assertEqual(form.parse(reply, target), want)
        self.assertEqual([form.receipt(ask), form.receipt(auto), form.receipt(keep)],
                         ["Approved; edits still ask", "Approved; edits are auto-accepted", "Keep planning"])

    def test_a_long_plan_is_cut_with_its_length_noted(self):
        form = PlanForm({"plan": "x" * 5000}, "proj")
        self.assertIn("x" * PlanForm.LIMIT + "\N{HORIZONTAL ELLIPSIS}", form.text)
        self.assertNotIn("x" * (PlanForm.LIMIT + 1), form.text)
        self.assertIn(f"first {PlanForm.LIMIT} of 5000 characters", form.text)
        self.assertEqual(len(form.polls), 1)

    def test_texts(self):
        self.assertIn("rm -rf build", PermissionForm("Bash", {"command": "rm -rf build"}, "proj").text)
        self.assertTrue(ContinueForm("x" * 2000, "proj").text.endswith("\N{HORIZONTAL ELLIPSIS}\n\nReply to continue "
                                                                       "this session."))
        self.assertEqual(texts.status([], 0, False), (f"Nothing is waiting for you.\n{texts.AWAY_OFF}", ""))
        text, tag = texts.status([MINE], 5 + 180, True)
        self.assertEqual((text, tag), (f"Waiting for you (1):\n[{ME}] Bash in proj: \N{MIDDLE DOT} 3 min ago\n"
                                       f"{texts.AWAY_ON}", ME))
        self.assertEqual(texts.hint([MINE, NEW])[1], "")  # several waiting: a plain reply counts for none

    def test_a_digest_lists_each_session_by_tag_project_and_first_line(self):
        long = "Here is the audit of the eight gates, one paragraph each:\n\n" + "x" * 1400
        forms = [ContinueForm("Tests pass. I pushed the branch fix-hashes.", "ziran-paper"),
                 ContinueForm(long, "wuwei"), ContinueForm("y" * 200, "big")]
        self.assertEqual([f.first for f in forms],
                         ["Tests pass. I pushed the branch fix-hashes.",
                          "Here is the audit of the eight gates, one paragraph each:\N{HORIZONTAL ELLIPSIS}",
                          "y" * 80 + "\N{HORIZONTAL ELLIPSIS}"])
        self.assertEqual(ContinueForm("\n\n  \nDone.", "p").first, "Done.")
        self.assertEqual(ContinueForm(None, "p").first, "Finished its turn.")
        for blank in ("  \n", "\t", "\u2028"):  # whitespace only: today's message, never an error
            with self.subTest(last=blank):
                form = ContinueForm(blank, "p")
                self.assertEqual((form.first, form.text), ("Finished its turn.",
                                                          "p:\nFinished its turn.\n\nReply to continue this session."))
        sent_at = 1_800_000_000
        text = texts.digest([("a3f1", "ziran-paper", forms[0].first, None), ("7c20", "wuwei", forms[1].first, None),
                             ("e9b4", "signal-plugin-cc", "ignored", sent_at)])
        at = texts.clock(sent_at)
        self.assertEqual(text, "3 sessions finished:\n"
                               "[a3f1] ziran-paper: Tests pass. I pushed the branch fix-hashes.\n"
                               "[7c20] wuwei: Here is the audit of the eight gates, one paragraph each:\N{HORIZONTAL ELLIPSIS}\n"
                               f"[e9b4] signal-plugin-cc: (sent at {at}, above)\n\n"
                               "Start a reply with a tag to continue that session, "
                               "or pick one in the poll to read it in full.")
        self.assertRegex(at, r"^\d\d:\d\d$")
        self.assertEqual(texts.option("a3f1", "p" * 200), "[a3f1] " + "p" * 93)  # signal-cli: 1 to 100 characters


if __name__ == "__main__":
    unittest.main()
