Verdict: PASS
Gate: quality
Item: mac-answer-notice
PR: taoq-ai/signal-plugin-cc#6
Head: 8baf808d323192403dfd58dff50e2eb49bed9145
Confidence: high
Breaking: no

## Findings
- [low] tests/test_adapters.py blocks: no. Untested (carried from quality-415039f.md): listen with the headless guard moved after quiet() passes all 75 tests, because no test starts a headless listen with a live listener registered for the session. Missing test: register a listener pid, run listen under headless, assert the pid is not signalled and its entry is kept. The order was main's before this PR, so it is not from this delta.

## Probes
- Merge shape: 8baf808 parents are 415039f and a6b13f8 (origin/main, unchanged after fetch). `git diff 415039f 8baf808 --stat` shows only main's #5 and #7 files (forms.py, plugin.json, marketplace.json, README, ADR, tests) plus the two import-line resolutions in hooks.py and test_app.py.
- PR diff against main unchanged: the +/- lines of `git diff c7d7222 415039f` (old base) and `git diff origin/main 8baf808` (new base) are identical (diff of the changed lines empty); both are 8 files, 157 insertions, 10 deletions... the new one is 8 files (README, processes.py, conversation.py, model.py, texts.py, hooks.py, test_adapters.py, test_app.py).
- Both conflict sides kept: hooks.py imports `PlanForm` (forms) and `AT_MAC, CLOSED` (model); test_app.py imports `PlanForm` and `AT_MAC, CLOSED, Stopped`. compileall clean. No NOT_RELAYED reference remains in signal_cc or tests.
- Test names: unique `def test_` names at 415039f (69) and at a6b13f8 (68) union to exactly the 75 at 8baf808 (sorted-unique diff empty); no duplicate names. The merged test_at_the_mac_nothing_is_sent now loops over BASH and a PlanForm, so the Mac-takeover path covers the new form.
- Tests on a `git archive 8baf808` copy: python3.14.5 `python3 -m unittest discover -s tests` Ran 75, OK; /usr/bin/python3 3.9.6 Ran 75, OK. No skips reported.
- listen order (hooks.py:62-64) still `if processes.headless(): return None` then `quiet(cfg, hook)`. Mutant swapping them: 75 OK, survives (the finding above, a note).
- quiet still sends the stop reason (hooks.py:53 `processes.stop(pid, AT_MAC if typed else CLOSED if event == "SessionEnd" else None)`). Mutant `processes.stop(pid)`: killed by test_quiet_tells_the_listener_why_it_stops, 2 subtests (UserPromptSubmit expects SIGUSR1, SessionEnd expects SIGUSR2). Both mutants re-run in fresh copies of the head.
- CI run 40919013553 cited as green on all three legs; not re-fetched (call budget). Local runs match.
- Remaining "signal-plugin-cc" strings (config dir, WOKEN, stderr prefixes) are unchanged context from main's #7, not this PR's change.
- closed: merge-conflict finding (import-line only, keep both) at 8baf808.
- Simplicity: none. The merge adds no code of its own; the two import lines are both used.

## Residual risk
The headless-before-quiet order is pinned by no test (inherited from main). Nothing else in the merge differs from the PR already judged at 415039f.
