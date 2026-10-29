Verdict: FIX
Gate: arch
Item: leave-digest
PR: taoq-ai/signal-plugin-cc#12
Head: d46d75ef4c4d1d9c09760dc025d09fd1829e6ac4
Confidence: high
Breaking: no   (minor: relay.log gains an optional `digest` key, config home gains gather/ and gather.lock, gather entries gain a `pid` key; no documented element removed or reshaped)

## Findings
- [high] signal_cc/adapters/files.py:158 blocks: yes. Failure: in production, a member taken over at the Mac writes `gone` into its entry and then its listener process exits. The next `entries()` call finds that pid dead and deletes the file, so the gone set is empty from then on. A tag or a poll pick of that member gets silence instead of "That session no longer listens here", and with an older prompt outside the digest waiting, the tag gets the "Which prompt?" hint again (the old P4 case). This happens every time, not in a race: the listener always exits right after its STOPPED notice. The app tests miss it because FakeGathering has no pid, and the adapter test only drops an entry without `gone`. Fix: keep an entry with `gone` set even when its pid is dead (for example `if row.get("gone") or alive(...)`), and leave its removal to the next lead as before. Add an adapter test whose `gone` entry was written by a child process that has exited (regression of acceptance 5, introduced by this fix round)
- [medium] signal_cc/app/conversation.py:61 blocks: yes. Failure: a session that finds the owner already away enters the gathering with sent None, and records sent only after its own message has gone out (line 66). If a lead reads the entries while that send is in flight, the session is listed in the digest and poll as a session that finished at the Mac, and it also sends its own message. A poll pick of it then gets silence: its listener does not hold the poll, and the other members skip it. Probe P3 reproduced this in 3 of 3 runs with a 0.5 s send. A real signal-cli send takes that long or longer, against a 10 s gather window. This contradicts the mock's rule, which the fix itself adopts at continue_session: a session that did not wait in the presence loop does not go out in a digest. The race is new in this round, because before it every session went through _gather. Fix: on the non-join path, send first and then enter with sent already set (or mark the entry as not joining, so the lead never takes it as a member) (spec contradiction, charter rule 1; promise: a poll pick reaches that session)
- [low] signal_cc/app/conversation.py:63 blocks: no. PR #14 merge hazard. In the trial merge (`git merge-tree d46d75e 2227f93`), #14 fills `sent` with the session's earlier timestamps before the send, so `if not sent:` is False. A session with kept earlier messages then never sends its own finished-turn message. #14's `keep(self.session, tag, ts)` also lands outside the conflict, where `ts` is undefined on the digest path, so a resolver would be tempted to bind it to the digest's text timestamp. What to do now: let `_gather` return the digest explicitly, decide with `if not joined:` rather than `if not sent:`, and name the own message's timestamp (`own = None` when the session went out in a digest). The merge then reads `if thread and own is not None: keep(...)`, and the digest's text and poll timestamps are never kept
- [low] signal_cc/domain/routing.py:34 blocks: no. PR #14 merge hazard. Both PRs add a sixth positional parameter to route (`gone=()` here, `mine=(), kept=()` in #14), and both call sites pass it positionally. A merged signature with the old #14 call would shift `mine` into `gone` and `kept` into `mine`, so a session would take replies tagged for other sessions' kept messages. What to do now: make `gone` keyword-only (`*, gone=()`) and call it `gone=gone`. The order to record for whichever PR merges second: a live tag; then #14's `mine` (Take); then this PR's digest-member block and gone-skip; then #14's `kept` (SKIP); then quotes. This order holds because a tag can be both mine and a digest member only if a claim reuses a kept tag, which #14 forbids. The gone block must come before `kept`, or a forget racing with the stop would suppress the Gone answer
- [low] signal_cc/domain/routing.py:59 blocks: no. The mutant `len(picked) != 1` to `not picked` survived in two fresh copies. A single-choice poll sends one index, so there is no concrete input to name; the PR records this
- [low] signal_cc/app/conversation.py:74 blocks: no. Still open from round 1, and the PR records it: a follower stopped in the STEP window, after the lead wrote the digest into its entry but before the follower read it, sends no notice and marks no gone

## Probes
- Suite at the head (`python3 -m unittest discover -s tests` in a `git archive d46d75e` copy, Python 3.14.5): 108 tests OK in 50.1 s. tests/test_architecture.py passes (layer rule; FileGathering built only in entry/wiring.py).
- P1 (probes/gone_probe.py, real FileGathering): a child process enters aaaa and runs update(gone=...), then exits. The child sees gone; the parent's entries() afterwards returns ['bbbb'] with an empty gone set, and the aaaa file is deleted. route("[aaaa] go on") from b gives skip; with gone={'aaaa'} it gives Gone.
- P2 (probes/e2e_gone.py, the DigestTest harness on a real FileGathering, with a's entry pid set to a reaped child after a exits). Each of two runs gave: tag of a → [] (silence); poll pick of a → [] (one earlier run showed b's message, from the test helper's tag-order assumption: digest order follows entry time, not claim order); control with pid alive → "[a] That session no longer listens here"; older prompt e waiting → "Which prompt? 2 waiting", which is the old P4 hint returning.
- P3 (probes/race_join.py): a and b finish at the Mac and the owner leaves. During the lead's gather, d finds the owner away and its send takes 0.5 s. All 3 runs sent "3 sessions finished: … [d] d: Done." with d in the poll, plus d's own message. d's entry holds both the digest and its own sent time. A pick of d in the poll → [].
- Mutants, each in a fresh archive copy with the full suite:
  - join always: killed by test_sessions_finishing_after_the_digest….
  - join never: killed by 8 tests, test_two_listeners_wired… among them.
  - gone non-member skip removed: killed by test_a_tag…older_prompt_waits and the domain table.
  - pick → SKIP instead of gone_or_skip: killed by test_a_poll_pick_of_a_session_taken_over… and the table.
  - `0 <=` dropped: killed by the table.
  - alive() ignored: killed by test_gathering_shares_entries….
  - lead purge removed (old M7): killed by test_an_entry_whose_listener_is_gone….
  - `len(picked) != 1` → `not picked`: survived twice.
- Trial merge with PR #14 (`git merge-tree --write-tree d46d75e 2227f93`): conflicts in README.md, conversation.py, routing.py, tests/test_adapters.py and tests/test_domain.py. wiring.py merges cleanly, contrary to the brief. Read the conflict hunks; hazards are in the two notes above.
- closed: conversation.py:205 (gather for every turn) at d46d75e; join=waited, mutants J1 and J2 killed. A session that finds the owner away is no longer delayed 10 s.
- closed: routing.py:57 (silent poll pick of a taken-over member) at d46d75e in logic and the fake harness. In production it reopens through the files.py:158 finding.
- closed: routing.py:46 (two answers per tag) at d46d75e in logic. In production it reopens through files.py:158 (P2, older-prompt run).
- closed: conversation.py:116 (no cleanup tested) at d46d75e; M7 killed.
- closed: conversation.py:93 (every member ends the poll) at d46d75e; test_three_finished… asserts the poll stays open after a wakes.
- closed: conversation.py:131 (OSError from send_poll) at d46d75e; test_a_poll_that_cannot_be_sent….
- closed: ports.py:42 (Gathering docs, gone and digest shape, README four ports) at d46d75e.
- Confidence high: the first finding is a deterministic read of entries() against the listener's exit path (hooks.quiet → processes.stop → SystemExit → exit), reproduced across real processes. The second is reproduced in 3 of 3 runs.

## Residual risk
Once gone entries survive their listener's exit, a reused pid can keep a SIGKILLed entry alive. The lead's `not in live` check still drops it once the claim lapses. The two PR #14 merge hazards are not defects at this head, but the second PR to merge will cross sessions unless it follows the order and keyword rules above.
