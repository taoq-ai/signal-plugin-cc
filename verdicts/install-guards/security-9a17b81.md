Verdict: PASS
Gate: security
Item: install-guards
PR: taoq-ai/signal-plugin-cc#4
Head: 9a17b8163109c767b7589412f61d3fe4740dd3e5
Confidence: medium

## Findings
- [low] signal_cc/adapters/processes.py:26 blocks: no. The argv check splits ps output on whitespace, so prompt text counts as flags. A claude -p run whose prompt holds the token --input-format=stream-json is judged not headless, and the listener starts as it did before this PR. An interactive run whose prompt holds " -p " is judged headless and gets no Stop listener. Combined short flags (-cp) are not recognised. None of these is a regression from base, and the inputs come from the same user who starts claude, so no trust boundary is crossed (CWE-807, limit).
- [low] signal_cc/adapters/processes.py:22 blocks: no. The pid.isdigit() guard has no test. With it removed, CLAUDE_PID="1,<pid>" or "1 <pid>" makes ps read several processes (the mutant shows headless flipping to True), and the suite still passes. A test that sets CLAUDE_PID to a comma or space list would catch it.
- [low] signal_cc/entry/cli.py:21 blocks: no. When ps is missing from PATH, headless() raises FileNotFoundError. cli.main catches it as OSError and prints "signal-cli daemon on port N: ... 'ps'", which is misleading. It fails closed (exit 0, no listener recorded).
- [low] signal_cc/adapters/processes.py:22 blocks: no. subprocess.run(ps) has no timeout. This is the same as the existing is_relay.
- [low] blocks: no. No secret, dependency or static-analysis scanner exists in the repository or its CI, so that coverage is unmeasured, not clean. hooks.json and the agent tooling are unchanged.

## Probes
- PR #4 head read once: 9a17b81, draft, base main.
- Tests: `python3 -m unittest discover -s tests` on a git archive copy with HOME set to scratch. Ran 41, OK (Python 3.14.5).
- Injection: a stub ps on PATH logged its argv for 22 CLAUDE_PID spellings ("", abc, -1, -A, "1;id", "$(id)", "1 2", "1,2", superscript 2, Arabic-Indic digits, 0, 30 nines, " 1", "1\n", +1, leading-zero pid, live pids, pid 1, own pid) under entrypoints cli and sdk-cli. Every ps call was exactly [-o][command=][-p][<digits>]. Values with a dash, a space, a comma, a sign or a shell metacharacter never reached ps. Unicode digits reached ps, which rejected them, and the code fell back to CLAUDE_CODE_ENTRYPOINT. No shell is used (list argv).
- Fail-open: a malformed or absent CLAUDE_PID falls back to the entrypoint check (sdk-cli gives True). Positive: a live stand-in with "-p x" gives True even with entrypoint cli. Negatives: interactive and stream-json input give False. CLAUDE_PID naming another process (pid 1) overrides sdk-cli and gives False. Before this PR the listener always started, so every miss equals base behaviour.
- Early exit: relay.py calls sys.exit(0) before any import of signal_cc. The fcntl test (sys.modules['fcntl']=None, all six handlers, with a config present) gave rc 0 and empty stdout and stderr.
- Missing ps: relay.py listen with PATH lacking ps and CLAUDE_PID=123 gave rc 0, one misleading stderr line, and no listener file in SIGNAL_CC_HOME (port 1, no network).
- Mutants, each in a fresh archive copy. Removing the listen guard: test_listen_in_a_headless_run_returns_at_once fails. Dropping "not streaming": test_interactive_and_streaming_sessions_are_not fails (2). Changing sys.exit(0) to pass: test_without_fcntl_every_hook_exits_silently fails (6). Making the fallback return False: test_without_the_claude_process_the_entrypoint_decides fails. Removing isdigit: survives, re-run in a fresh copy and still OK (41 tests). Untested, see Findings.
- Supply chain: no new dependencies. The workflow runs on pull_request with permissions contents: read, and only the matrix changed. plugin.json homepage and repository point to the repository's own GitHub URL.
- Confidence is medium: CLAUDE_PID being set by Claude Code in a real hook environment was not observed here (goal gate, rewake-probe). Linux procps width truncation of `ps -o command=` was not measured.

## Residual risk
The guard trusts process argv and environment the same user controls. A miss restores the base behaviour (a Stop listener in a claude -p run), not a new exposure.
