Verdict: PASS
Gate: security
Item: land-status-ci
PR: taoq-ai/signal-plugin-cc#1
Head: a3f918a1c248d5c527029bb9adfbb3f8faa94cb2
Confidence: medium

## Findings
- [low] tests/test_adapters.py:121 blocks: no. The test asserts other.poll() right after SIGTERM, so it cannot see the kill: reversing the "relay.py" check in signal_cc/adapters/processes.py:14 survives (3 runs, plus a fresh copy). With a 0.5 s wait before the assert, the mutant fails. The base had the same gap (tests/test_relay.py:263 at 8f0252e). If this check ever regressed, a stale pidfile whose pid was reused would SIGTERM an unrelated owner process (CWE-283). Suggested fix: other.wait(timeout=1) inside assertRaises(TimeoutExpired).
- [low] signal_cc/adapters/files.py:85 blocks: no. No test covers the pid guard in Listeners.clear: `if True:` survives, and the same mutant on base hooks.py:142 also survives. If it regressed, a superseded listener's finally block would delete the newer listener's pidfile. quiet() then could not stop that listener, and a late Signal reply would wake the session after the owner went back to the Mac (CWE-367).
- [low] signal_cc/adapters/processes.py:14 blocks: no. No test covers the guard against killing its own pid: dropping `pid != os.getpid() and` survives. The worst case is a listener that SIGTERMs itself on a stale reused pidfile and drops one relay.
- [low] signal_cc/adapters/files.py:70 blocks: no. Existing gap, carried over from base hooks.py:100: session_id from the hook JSON goes into the pidfile path without validation. Probe: Listeners(home)._path('../../escape') resolves to home/listeners/../../escape.pid (CWE-22). Claude Code sends UUIDs, so this is not reachable from Signal.
- [low] .github/workflows/tests.yml:1 blocks: no. The workflow has no `permissions:` block, and actions/checkout@v4 and actions/setup-python@v5 are pinned by tag, not by SHA. Today the repo's default token is read (gh api actions/permissions/workflow), and the trigger is pull_request, not pull_request_target, with no secrets. Suggested hardening: `permissions: contents: read`.
- [low] blocks: no. Repo setting, outside the diff: can_approve_pull_request_reviews is true. A workflow that requested pull-requests: write could approve a PR that needs owner review. This workflow requests no such permission.

## Probes
- Diff 8f0252e..a3f918a (33 files, +1383/-753): a move of ask/daemon/hooks/presence into domain/app/adapters/entry, plus the desk (`relay.py desk`, started by SessionStart, flock'd to one per Mac), the `status` command, cli handling of empty stdin, and the CI workflow. No new dependencies (stdlib only), no install scripts, no secrets. A grep for token, key and phone patterns found only test fixture numbers (+1555...).
- Scanner: the repository has none (its CI runs unittest only). gitleaks, trufflehog, bandit and pip-audit are not installed. Secret, dependency and SAST scanning: unmeasured.
- Tests at head in a git archive copy (Python 3.14.5): Ran 33, OK.
- Owner filter (trust boundary): the parse_event check at signal_cli.py:83 now runs before the sync unwrap; the semantics match base daemon.py:97. Mutant (drop the return) killed by test_events_become_replies_from_the_owner_only. Mutant to_self=True killed by the same test (and it hangs the listen test).
- Desk end to end against the stub daemon (tools/desk_probe.py), one prompt waiting. Negative cases, each 0 sends: non-owner "status" in bot mode; non-owner in note-to-self; the owner writing "status" to someone else; sourceNumber non-owner with source=owner. Positive cases, each 1 send: owner " STATUS " in bot mode; owner note-to-self sync. The desk exits when the stream ends in every case.
- Routing: in the command() guard, the mutant dropping `quoted is None and votes is None` was killed by DeskTest and RoutingTest; removing the route() SKIP was killed by test_a_plain_command_is_never_taken_as_an_answer and RoutingTest; the desk `if True:` mutant was killed by test_answers_status_and_nothing_else.
- Desk mark_latest race: route() takes a plain reply only when exactly one prompt is live AND latest == that tag, so an interleaved claim or release yields HINT or SKIP, never a cross-session approval. The single-prompt plain reply after `status` has the same semantics as the base hint (base ask.py:67).
- DeskLock: removing flock was killed by test_one_desk_lock_at_a_time. Widening BlockingIOError to OSError behaves the same here (not listed).
- Process spawn: Popen([sys.executable, <resolved relay.py>, "desk"]) with no shell and no input from the hook or Signal. The kill path is still gated by the ps "relay.py" check plus the own-pid check (see Findings for test strength).
- CLI fails closed with a closed port (9) and a temp SIGNAL_CC_HOME: empty stdin, missing tool_name, unknown handler, no handler, bad JSON and missing questions all give rc=0, empty stdout and a traceback on stderr, so Claude Code falls back to the Mac.
- Workflow and repo: gh api shows the repo is private and default_workflow_permissions=read; PR #1 headRefOid matches the reviewed head and is a draft.
- Confidence medium: the security surface is small and probed with positive and negative cases, but no scanner ran, and the real signal-cli SSE fan-out to the desk plus several prompts was not exercised (port 8299 was off limits).

## Residual risk
The kill and pidfile guards are correct at head, but their tests are weak or missing (an existing gap since base), so a later regression there would go uncaught. Secret and dependency scanning are unmeasured.
