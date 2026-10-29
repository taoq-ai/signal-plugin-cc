Verdict: PASS
Gate: quality
Item: land-status-ci
PR: taoq-ai/signal-plugin-cc
Head: a3f918a1c248d5c527029bb9adfbb3f8faa94cb2
Confidence: medium
Supersedes: none

## Findings
- [low] tests/test_adapters.py:121 blocks: no. Carried over unchanged from main: assertIsNone(other.poll()) is checked right after the SIGTERM, so it passes before the process dies. With the is_relay `"relay.py" in cmd` check removed, an unrelated process is killed, yet all 33 tests pass (4 of 4 runs). Wait briefly before polling, or kill-then-wait and assert the exit code.
- [low] signal_cc/entry/hooks.py:80 blocks: no. Untested: no test calls hooks.start, so deleting the processes.spawn("desk") line leaves all 33 tests green. A real `relay.py start` does start one desk (probe under Probes).
- [low] signal_cc/entry/hooks.py:88 blocks: no. Untested: run_desk's single-instance guard (`if not lock.acquire(): return None`) has no test, only DeskLock itself does. The stub daemon hands each event to one connection, so it cannot show the double reply two desks would give on a real daemon.
- [low] signal_cc/app/conversation.py:34 blocks: no. Untested: a prompt's claim now lasts `wait`, not cfg.wait (a listener's claim lives 3600 s, not 300 s). The commit message states the change; mutating it back to self.wait keeps all tests green. Add one registry-level assertion on the ttl passed to claim.
- [low] signal_cc/ports.py:17 blocks: no. The annotation `Tuple["queue.Queue", ...]` names queue, which is never imported (a lint error; typing.get_type_hints would fail).
- [low] tests/test_architecture.py:30 blocks: no. Only relative imports are checked, so `from signal_cc.adapters import x` inside domain passes (probed: 0 failures). The package uses relative imports throughout, so this is a limit, not a defect.
- [low] .github/workflows/tests.yml:1 blocks: no. No `permissions:` block (the token keeps the repo default) and the actions are pinned by tag (@v4, @v5), not by sha.
- [low] tests/test_adapters.py:26 blocks: no. Process-wide state leaks across tests: macos.idle_seconds is replaced and never restored, conversation.SETTLE and POLL are overwritten, and hooks.listen installs a SIGTERM handler in the test process. Harmless today.

## Probes
Baseline: `git archive a3f918a` into a clean folder, `python3 -m unittest discover -s tests`: 33 tests OK on 3.14.5 (13 s), 3.9.6 and 3.11.15. 33 collected, 0 skipped. Python 3.10 (the CI version) is not installed here: unmeasured; 3.9 and 3.11 bracket it and the code uses no 3.11-only syntax. origin/main: 18 tests OK.
Mutants (each in a fresh archive copy; 53 run). Killed, with the test that fails: route command skip (test_a_plain_command_is_never_taken_as_an_answer, test_a_reply_never_crosses_to_another_prompt); command() quoted check (test_answers_status_and_nothing_else); desk status-only filter and desk mark_latest (test_answers_status_and_nothing_else); registry expiry (test_claims_never_reuse_a_waiting_tag_and_expire); end_poll in finally; release; presence away; mark-before-send; hint tag; status tag; tagged-for-me; latest check; hint-from-oldest; quoted-in-sent; skin tones; pick multi; continue limit; listen exit 2; cli no-config; note-to-self; rpc error; withdrawn vote. Hangs count as killed: DeskLock non-blocking flag; owner filter; continue_session grace.
Survived, all reported above or as carried over: command() votes check, claim ttl, is_relay pid and name checks, hooks.start spawn, start daemon check, run_desk lock, desk daemon wait, stale-claim purge in claim(), Listeners.clear pid guard, poll-failure break (single-poll test), poll mark_latest, multi-select settle, leave_on_return, status multi-prompt hint line, NOT_RELAYED, SIGTERM handler, quiet-before-listen, cli OSError and Exception catches, empty-stdin, wiring idle, macOS returned/away, end_poll quiet flag, reaction isRemove. Most of these were also untested on main; the status desk lines are new.
Probe, desk end to end: a stub daemon on a random port (not 8299), a temp SIGNAL_CC_HOME, and the real `relay.py start`. It started one desk process; a second `start` left one (the lock held); a `status` message got "Nothing is waiting for you." back; after the stream ended the desk exited. Nothing was sent to a real Signal. No stray processes remain.
Probe, architecture test: an outward import from domain to app, from domain to ports, from domain to adapters, from app to adapters, from app to config, from adapters to app, from ports to app and from a new domain module to adapters each fail the test (8 of 8). Absolute imports of signal_cc.* pass it (finding above).
Behaviour preservation: ask, hints, receipts, timeouts, poll marking and listener cleanup were diffed against main's ask.py and hooks.py and match. The two intended differences are the claim lifetime and a desk-era empty stdin ({} to handlers). Both are stated or harmless.
Simplicity: none to delete. The three Protocols have in-memory fakes as second implementations and the layering is enforced by test_architecture; Config.pending was already removed.

## Residual risk
The CI matrix's 3.10 run and the Ubuntu runner are unmeasured here; the first PR run is the evidence. The new untested spots are the desk's startup and its single-instance lock.
