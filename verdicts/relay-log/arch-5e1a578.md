Verdict: PASS
Gate: arch
Item: relay-log
PR: taoq-ai/signal-plugin-cc#3
Head: 5e1a578ef403f1dd301111ad63113a7ec844d6c7
Confidence: high
Breaking: no (minor: a new append-only local file, one more documented outcome value and an issue template; Conversation is internal, built only in wiring.py)

## Findings
- [low] signal_cc/app/conversation.py:39 blocks: no. Keeping an outcome that is already named on SystemExit has no test. A mutant that always records `quieted` survives two fresh runs, and so does a mutant that drops "send failed" from the tuple. The probe shows the head is right in both windows. A test that raises SystemExit during the closing receipt send and expects `answered` would cover the first.
- [low] blocks: no. Under the promise, the outcome set is fixed at six values. Fix round 1 adds a seventh, `quieted`, and it covers three causes: typing at the Mac, the next Stop, and the session closing. So for continue prompts, acceptance 2's "back at the Mac" is not told apart from the other two causes. The PR body records this as a two-way assumption ("the listener cannot tell which hook stopped it"). `hooks.quiet` does know `hook_event_name` and could record the cause if G-2 ever needs the split. The goal gate should weigh whether the extra value fits the promise.
- [low] tests/test_adapters.py:181 blocks: no. Nothing cancels the threading.Timer. If hooks.listen raises something other than SystemExit before 1 s, the finally puts back the default SIGTERM handler, and the timer's SIGTERM then kills the whole test run instead of reporting one failure. Calling `timer.cancel()` in the finally would fix it.
- [low] blocks: no. Carried from a272648: prompts kept at the Mac get no line, so relay.log cannot show G-2's "0 missed prompts" when presence wrongly says the owner is at the Mac. The PR body records this under Assumptions. The goal gate should weigh it.

## Probes
- Read the previous verdict (arch-a272648.md), `wuwei plan show relay-log`, .wuwei/goals.md and the PR body (read once). `git diff a272648 5e1a578` shows 5 files, +81/-20. `git ls-remote` confirms that feat/relay-log is still at 5e1a578 at verdict time.
- Tests on a `git archive 5e1a578` copy: `python3 -m unittest discover -s tests` ran 49 tests, OK. With `-p test_architecture.py`, 3 tests passed (layers point inward, and only wiring builds the port adapters).
- Dependencies: the delta adds no imports to signal_cc. conversation.py still imports only domain, and no cycle appears. The layering rule is the repo's one stated fitness function, and it holds. No line or config-key budget is stated, and the config key count is unchanged.
- Contract: relay.log now has the outcome `quieted`. The README lists every outcome, the keys of both line shapes, the two lines a failing prompt gives ("count prompts by the lines with kind") and $SIGNAL_CC_HOME. config.py:34 agrees on the home. No code reads relay.log. cli.main catches only Exception, so the SystemExit raised again from ask does not add a handler error line.
- SystemExit probe (scratchpad r1/probe/keep_named.py), using continue_session with the fakes. SystemExit during the first send gives ['quieted']. SystemExit during the receipt send after an answer gives ['answered'], so the named outcome is kept.
- Mutants, each in a fresh git-archive copy. These are killed: removing the quieted branch (2 tests), removing the "send failed" mark before say (test_each_way_a_prompt_ends_is_named), starting the outcome at "send failed" (test_a_daemon_that_cannot_be_reached_is_an_error_not_a_failed_send), dropping failed() in the cli OSError branch (subTest start), dropping the HANDLERS guard (subTest bogus-hush), and always recording "stream ended" (test_a_stream_that_ends_after_the_answer_records_answered). Two mutants survive and survived a second fresh run: `if True:` in place of the outcome check, and the tuple without "send failed".
- closed: conversation.py:50, a quieted listener logged as error, at 5e1a578 (the real SIGTERM through hooks.listen now logs `quieted`; acceptance 7)
- closed: cli.py:28, the OSError branch untested, at 5e1a578
- closed: conversation.py:83, a stream that ends inside the settle window untested, at 5e1a578
- closed: cli.py:15, the handler guard untested, at 5e1a578
- closed: README.md:108, the failure line's keys and the double count, at 5e1a578
- closed: README.md:106 and relay-failure.md:13, the SIGNAL_CC_HOME path, at 5e1a578
- Confidence high: every closed finding was re-checked by a mutant or by reading the head, and the one open behaviour risk (a SIGTERM after the outcome is named) was probed directly.

## Residual risk
A SIGTERM during the receipt send after an answer records `answered`, but the reply never wakes the session. The window is narrow, and the behaviour was there before this PR. The permission path still installs no SIGTERM handler, so a hook that Claude Code kills leaves no line. Concurrent appends were not stress-tested.
