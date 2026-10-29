Verdict: FIX
Gate: security
Item: leave-digest
PR: taoq-ai/signal-plugin-cc#12
Head: d46d75ef4c4d1d9c09760dc025d09fd1829e6ac4
Confidence: high

## Findings
- [medium] signal_cc/adapters/files.py:158 blocks: yes. Failure: the Mac takes over digest member a3f1, so its listener writes gone=AT_MAC, skips leave() and exits; the next entries() call from any listener sees a dead pid and deletes gather/a3f1, so gone is empty when the owner later replies "[a3f1] x" or picks a3f1 in the poll, and every listener returns SKIP: Signal stays silent instead of saying "That session no longer listens here". At 40fa908 the same probe gives Gone(a3f1). The fix commit added this, which contradicts its own comment at conversation.py:93 ("a gone entry stays until the next digest's lead clears it"). Nothing is delivered and no session wakes, so this fails closed (requirement: acceptance 5; regression from 40fa908). Fix: keep gone rows whatever the pid, e.g. `if row.get("gone") or alive(row.get("pid")):`, and add an adapter test where a child process sets gone and exits. That mutant passes the suite today, because FakeGathering never drops rows by pid.
- [low] signal_cc/domain/routing.py:60 blocks: no. Untested: the mutant `len(picked) != 1` -> `len(picked) == 0` survives two fresh runs. A multi-index vote then reaches gone_or_skip with an arbitrary member, which can give at most one GONE notice and never a SHOW or Take. The single-select digest poll can't send one. Add a [0, 1] vote row to the domain table.
- [low] signal_cc/app/conversation.py:63 blocks: no. Race, read but not run: a session that found the owner away (join=False) enters with sent=None, then sends its own message. A lead whose GATHER sleep ends in that window lists it as a digest member. Its listener never holds the Digest, so a poll pick of it, or a digest quote when it is the oldest member, gets silence. Its own tag still takes it alone, and nothing crosses.
- [low] signal_cc/adapters/files.py:179 blocks: no. alive() raises OverflowError on a pid beyond C long, and entries() raises AttributeError on a JSON row that is not a dict. Both need a hand-edited 0600 file in the 0700 home the user owns, so they are not a trust boundary.
- [low] blocks: no. No secret, dependency or static-analysis scanner runs in this repository (.github/workflows/tests.yml runs only unittest), so scanner coverage is unmeasured. A manual grep of origin/main...d46d75e for secrets and numbers found only the test fixture +15550000002. Nothing outside signal_cc/, tests/ and README.md changed, so no dependency, lockfile, workflow or hooks.json change.

## Probes
- closed: whitespace-only last message raises IndexError (forms.py:155) at d46d75e. "   ", "\n\n", "\t", " ", "\x0b\x0c", "\x1c\x1d\x1e", " 　", "" and None each give "Finished its turn." in both first and text, with no exception. test_domain covers three of them. Reverting the line gives 3 errors in the suite.
- closed: vote index -1 picks the last option (routing.py:57) at d46d75e. Votes [-1] and [-3] now pick nothing, and the mutant that drops `0 <=` is killed by test_domain RoutingTest.test_a_reply_to_a_digest_reaches_one_session_or_none.
- closed: untested `== {me}` (routing.py:57) at d46d75e. That line was replaced by `len(picked) != 1`, and its own survivor is the note above.
- closed: untested digest poll end guard at d46d75e. The mutant is killed by test_three_finished_sessions_get_one_digest_and_a_tag_wakes_one.
- closed: untested dead-entry cleanup at d46d75e. The mutant is killed by test_an_entry_whose_listener_is_gone_is_dropped_not_listed.
- Suite on a `git archive d46d75e` copy with a temporary HOME: `python3 -m unittest discover -s tests`, Ran 108, OK. Nothing was sent to Signal, nothing called port 8299 (the stub daemon binds 127.0.0.1:0), and ~/.config/signal-plugin-cc was not touched (its mtime 19:55 predates this review).
- Routing probe, three-member digest (a3f1, 7c20, e9b4; text ts 100, poll ts 101), 29 replies, plus a question prompt bb00 outside the digest in four rows, bad=0:
  - Votes: [0] shows a3f1 only and [2] shows e9b4 only. [-1], [-3], [3] (out of range), [10], [0,1] and [] pick nothing. [0,0] shows a3f1 only.
  - Hints: a vote on the digest text, a reaction on the digest or its poll, a plain quote, a plain reply and an unlisted tag each get one hint from the oldest member.
  - Tags: a digest quote "[7c20] go" takes 7c20 only. "[a3f1] run the tests too" takes a3f1 only, with "run the tests too", and "[A3F1] x" takes a3f1 only.
  - Gone and answered members: a gone a3f1 tag or a pick of it gets Gone once, from 7c20, also with bb00 older. A gone pick of [-3] gets nothing. An answered a3f1 tag or pick is SKIP everywhere. A gone tag with no digest member live is silent everywhere.
  - Others: a stale poll vote and "status" get nothing, and "[bb00] y" takes bb00 only.
  - No reply wakes more than one session, and no vote or reaction wakes any session.
- Gone-entry probe with a real FileGathering in a temporary home (the blocking finding). A child process enters a3f1, joins a digest, sets gone=AT_MAC and exits. The parent's entries() then lists only 7c20, and gather/a3f1 is deleted. route("[a3f1] x") from 7c20 gives skip at d46d75e and Gone(a3f1) at 40fa908.
- gather/ files at umask 022: home 0700, gather/ 0700, entry 0600 with the writer's own pid, gather.lock 0600. A second process is refused the lead while it is held and granted it once released.
  - Symlinked gather/: enter() is refused with ELOOP and nothing is written to the target. leave() through it raises ENOTDIR from private.remove and keeps the target (fails closed).
  - Planted links in gather/: a link to a dead-pid JSON row is not listed, and the link is removed while its target is kept. enter() replaces a planted link without writing its target. update() on a link to non-JSON is a no-op, and leave() unlinks the link, not its target.
  - Symlinked gather.lock: refused (ELOOP), target kept.
  - A loose 0755 home is tightened to 0700, and no temp files are left behind.
- Mutants, each in a fresh archive copy with the full suite:
  - Killed: dropping `0 <=`, dropping the gone-SKIP outside the digest, making a gone pick never answer, alive() always true, join always true, catching only RuntimeError on the digest poll, computing gone only for digest holders, reverting the whitespace fix, dropping the poll end guard, dropping the dead-entry cleanup.
  - Survived, re-run in a second fresh copy: `len(picked) == 0` (note). The proposed fix `row.get("gone") or alive(...)` also passes the suite, which shows the gone case has no test.
- Confidence high: every blocking claim is shown by a direct probe against the real adapter at both heads.

## Residual risk
Follower listeners still wait on the lead's flock with no deadline. FileGathering.update stays a read-modify-write without a lock, so concurrent updates can lose a field. Both can mislist a session, but no path found lets a reply wake another session.
