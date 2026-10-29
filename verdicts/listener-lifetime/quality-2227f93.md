Verdict: PASS
Gate: quality
Item: listener-lifetime
PR: taoq-ai/signal-plugin-cc#14
Head: 2227f93d31ca2318abfa1fa62c59c2f89cf5d7f5
Confidence: medium
Breaking: no
Supersedes: none

## Findings
- [low] tests/test_domain.py:0 blocks: no. Untested: the tag match for an earlier message is case-insensitive (`tagged.group(1).lower() in mine` in domain/routing.py:42), but no test uses an upper-case tag. Reversing it (mutant M11) leaves all 102 tests green. Harm is small: with no other prompt waiting the reply is still taken, with the tag left in its text; with another prompt live it is hinted instead.
- [low] signal_cc/entry/hooks.py:72 blocks: no. Untested and unchanged in kind: `hook.get("prompt") or ""` guards a null prompt, and removing the guard (mutant M24) survives. Main's `WOKEN not in hook.get("prompt", "")` already failed on null, and Claude Code sends a string, so nothing regresses.
- [low] tests/test_adapters.py:416 blocks: no. The new end-to-end test waits on wall-clock timers (a 1.0 s Timer sends SIGTERM to the test process, a 200 x 0.02 s poll). On a very slow runner SIGTERM could land before `exit_on_sigterm()` installs the handler. The same pattern is already used at test_adapters.py:325 and :337, so it matches the repository's convention. Not the known ps-based flake; it did not occur in any of my 4 runs.
- [low] signal_cc/app/conversation.py:63 blocks: no. Known limit, already in the PR body: a listener stopped by a typed prompt can still call `keep()` just after `forget()`. The stale thread then blocks that tag from `claim()`, and replies to it are skipped for other sessions, until the one-day expiry.

## Probes
Tests, `python3 -m unittest discover -s tests` on a `git archive` copy of each tree:
- Head 2227f93: 102 tests OK on 3.14.5 and on /usr/bin/python3 (3.9.6).
- origin/main 3771618: 91 tests OK on both interpreters.
- The ps-based flake did not appear in any of the 4 runs.

Owner scenario, real `relay.py` processes against a stub daemon on a free port, with a temporary home and no use of 8299 or ~/.config. Script: scratchpad quality-listener-lifetime/probe/e2e.py.
- Setup: session C has its own message waiting. Session A's listener sends message 1. A task-notification UserPromptSubmit arrives for A. A's Stop hook fires again, so B starts and sends message 2.
- After the task-notification, on head: listener A stays alive, the away file stays, the listeners/sA.pid file stays, and threads/sA keeps message 1 (4 of 4 checks, in all 7 runs).
- B replaces A. A exits on SIGTERM.
- Quoting message 1 wakes B, exit 2, stderr carries WOKEN and the reply; C stays.
- Tagging message 2 wakes B; C stays.
- Tagging message 1 wakes B; C stays.
- Quoting message 2 wakes B.
- Quoting C's message wakes C only; B stays alive.
- Tagging C's tag wakes C only; B stays alive.
- A typed prompt after that stops B (SIGUSR1) and turns away off. threads/sA is gone, and a quote of message 1 then does not reach the new listener.
- The same script on origin/main: the task-notification stops A and turns away off (A alive: False, away on: False), and quote1, tag1, tag2 and quote2 are all dropped (B woken: False in 4 of 4). The head fixes the owner's report.

Mutants, in a full tree copy per mutant, 3.14: the null mutant passes (102 OK). 25 mutants: 23 killed, 2 survive (M11, M24; the findings above). M11 and M24 were each run once, in a fresh copy, and survived.
- Killed: self_started always False (M1), no lstrip (M2), wrapper matched anywhere (M3), wake text dropped (M4), no early return (M5), forget only on typed (M6), forget only on session end (M7), no forget (M8), no `mine` branch (M9), no `kept` skip (M10), claim ignores kept (M12), no thread expiry (M13), expiry reversed (M14), earlier messages not seeded (M15), not read (M16), not kept (M17), thread not requested (M18), `mine` empty (M19), `kept` empty (M20), a failed keep fatal (M21), keep for non-thread asks (M22), a damaged line fatal (M23), forget moved before the stop (M25).

Red-first: the PR body's red counts match the new tests failing without the change (M1, M5, M15 to M18 each fail the new tests). Each new test reaches the real hooks, the registry files or the Conversation, not only a fake. `FakeRegistry` mirrors the three new methods.

Standards: no PR-body, trust-boundary or data-loss gaps seen. `keep` and `forget` go through `private.py` (0600, no symlink, tested in PrivateHomeTest). A failed keep does not stop the listener (M21 killed). No temporary or rate-limit failure ends a long job here.

Simplicity: none to delete. The one `KEEP` constant, the three Registry methods and the `mine`/`kept` parameters each trace to a requirement, and the standard library already supplies the single-line append.

## Residual risk
The end-to-end test timers and the shared home on a real Mac are the unmeasured parts. I did not run a real Claude Code against it, so the task-notification prompt shape (starts with `<task-notification>` after whitespace) rests on the PR's assumption and the builder's transcripts.
