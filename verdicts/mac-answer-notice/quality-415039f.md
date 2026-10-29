Verdict: PASS
Gate: quality
Item: mac-answer-notice
PR: taoq-ai/signal-plugin-cc#6
Head: 415039f79f1073bee3879fb509584fded4ed3b8c
Confidence: medium
Breaking: no

## Findings
- [low] tests/test_adapters.py:276 blocks: no. Untested: reversing the order in listen (quiet() before the headless guard) passes all 69 tests, because no test starts a headless listen with a live listener already registered for the session. Missing test: register a listener pid, run listen under headless, assert the pid is not signalled and the entry is kept. The order was main's before the merge, so the gap is not from this delta.
- [low] tests/test_adapters.py:264 blocks: no. The sibling test_a_listener_quieted_mid_wait_is_logged_as_quieted restores only SIGTERM, but listen installs SIGTERM, SIGUSR1 and SIGUSR2 handlers, so its SIGUSR1 and SIGUSR2 handlers leak into the runner. The new test captures the leaked handler as its "before" and restores it, so the leak survives. Harmless today; the loop in the new test could be shared.
- [low] blocks: no. Origin/main has moved to 9947c90 (plan-approval) and merge-tree shows conflicts in signal_cc/entry/hooks.py and tests/test_app.py. Both are import-line only: `from ..domain.forms import ... PlanForm ...` against this branch's `from ..domain.model import AT_MAC, CLOSED[, Stopped]`. Resolve by keeping both lines.

## Probes
- Full-tree copy of 415039f (git archive): `python3.14 -m unittest discover -s tests` Ran 69, OK; `/usr/bin/python3` Ran 69, OK. Counts: 69 tests, 0 skipped listed.
- Both sides survive the merge: every `def test_` name in tests/test_{adapters,app,domain,architecture}.py at c7d7222 (main's) and at 1754306 (this branch's earlier head) is present at 415039f (comm -23 empty for all four files, both bases).
- Conflict resolution in signal_cc/adapters/processes.py (read at the head): headless() kept, then `stop(pid, why=None)` sends SIGNALS[why]; listen runs `if processes.headless(): return None` before quiet(). The existing headless test and the signal tests pass.
- Null mutant (README.md unchanged text) in a fresh copy: 69 OK, so the baseline is clean.
- Mutant m1, conversation.py:70 `except (OSError, RuntimeError)` to `except OSError`: killed by test_a_notice_that_cannot_be_sent_still_ends_quietly (error='RuntimeError'), the new subTest. The old test used OSError only, so this mutant survived at 1754306.
- Mutant m2, same line to `except RuntimeError`: killed by the same test (error='OSError').
- Mutant m3, the first test's restore loop reduced to restoring SIGUSR1 only (the old behaviour): 69 OK, survives. A handler leak is not observable by any test, so the fix is hygiene and no test can kill it; it is not a missing-test gap in the code. No blocking harm is named.
- Mutant m5, headless guard moved after quiet(): survives (see the first finding).
- CI run 40914940651 cited as green on all three legs; not re-fetched (one call budget). The local runs above match.
- closed: first-round findings on the notice path are closed at 1754306 in arch-1754306.md and quality-1754306.md; this delta touches only the test fixes and the merge.
- Simplicity: none. The restore loop over three signals is the smallest correct form; the subTest loop over two error types replaces two copies of the test.

## Residual risk
The headless-before-quiet ordering is not pinned by a test, and the handler leak across tests is untested hygiene. The next merge with 9947c90 needs the two import-line resolutions and a re-run of the 69 plus plan-approval tests.
