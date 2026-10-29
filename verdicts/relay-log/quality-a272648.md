Verdict: FIX
Gate: quality
Item: relay-log
PR: taoq-ai/signal-plugin-cc#3
Head: a2726486ebddf72fd778d12a03613fbe3c2d9a60
Confidence: medium
Breaking: no

## Findings
- [medium] signal_cc/app/conversation.py:50 blocks: yes. Failure: a listener that is quieted (hooks.quiet sends SIGTERM when the owner types at the Mac or a new turn ends; processes.exit_on_sigterm turns it into SystemExit) while its prompt waits is written as outcome "error", though nothing failed; the log then counts every normal end of a continue prompt as an error, which falsifies G-2's error count (promise: every relay outcome recorded so G-2's targets are counted; requirement: outcome error means a failure)
- [low] signal_cc/app/conversation.py:36 blocks: no. subscribe() or registry.claim() raising (daemon down, disk full) is recorded as "send failed" although no send was tried, because the default outcome is set before _ask; probe shows lines=1 outcome "send failed" for both. cli.py then adds a second "error" line for the same failure (OSError reaches the handler), so one failure counts twice if lines are tallied by outcome
- [low] tests/test_adapters.py:0 blocks: no. Untested: the cli.py OSError branch (daemon down, the commonest real failure) can lose its failed() call and every test passes (mutant "cli OSError not recorded" survived, re-run in a fresh copy); likewise argv[1] not guarded against unknown handler names, session id passed to the question and listen hooks (set to "unknown", survived), and the stream-ended-with-answer outcome (survived). The guarded code at the head is correct; these are missing tests
- [low] blocks: no. FileJournal relies on one text-mode write per line for atomic appends; lines over Python's 8 KiB buffer could split in theory. A probe of 8 processes x 300 appends, with session ids of 0, 100, 9000 and 30000 bytes, gave 2400 lines and 0 unparseable each time on macOS, so it is a note only

## Probes
- Tests at head: 45 pass on 3.14.5 and on /usr/bin/python3 3.9.6; origin/main 36 pass on both. tests/test_architecture.py passes at the head (new port and adapter keep imports inward). No test skipped.
- Mutants on a full `git archive` copy of the head (baseline passing, null mutant M0 survived as it must): 25 run, 20 killed, 5 survived plus the null; the survivors were re-run in a fresh copy and survived again. Killed: back-at-Mac, timed-out and stream-ended outcomes, error marker, send-failed default, tag, text leak, number leak planted in the adapter, session in permission hook, cli Exception branch, str(error) instead of type, journal OSError guard, mkdir, append mode, newline, time, waited, wiring home. One mutant (record outside finally) was a malformed mutation and is discarded, not counted; the raise paths are covered by test_each_way_a_prompt_ends_is_named and test_an_error_while_waiting_is_recorded_and_raised.
- Exactly one line per ask, probed with fakes: timeout, back at the Mac, stream end, send failure, exception while waiting, answer (tests), plus subscribe failure, claim failure, poll-send OSError, KeyboardInterrupt, SIGTERM, ContinueForm(None): each gave lines=1. The SIGTERM run (real os.kill with exit_on_sigterm installed) gave lines=1 outcome "error", the basis of the blocking finding.
- Privacy: the known-positive holds. Planting "text": form.text in the entry fails test_the_log_holds_the_outcome_but_no_message_text_or_number and test_an_answered_permission_prompt_is_one_line; planting a phone number in FileJournal fails the adapter and cli tests. The entry is built from fixed keys (kind, tag, session, outcome, waited) and cli records type(error).__name__ only; the "str(error)" mutant is killed. Coverage of the leak test is the permission form only; question and continue entries pass through the same single record call.
- Concurrent appends: see the note above; no interleaving observed.
- Label relay-failure exists (gh label list); the issue template asks for the relay.log lines; README documents the log.
- Simplicity: none to delete; the `end` dict threaded through _ask and _collect is the smallest way to get the outcome out of the finally, though a small result/exception mapping could replace it. FileJournal is the single implementation behind a Protocol, in line with the repo's existing ports.

## Residual risk
Outcome labels for interrupted and early-failing prompts are imprecise, so G-2's counts need the fix above to be trusted; the rest of the log (privacy, one line per ask, append safety) holds under probe.
