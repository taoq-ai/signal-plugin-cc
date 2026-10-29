Verdict: PASS
Gate: security
Item: relay-log
PR: taoq-ai/signal-plugin-cc#3
Head: b2c4f849f091913184bc40e89a6b22eba7f71c84
Confidence: high

## Findings
- [low] signal_cc/adapters/files.py:92 blocks: no. relay.log is created with the default umask (0644, measured under umask 022), in a home that mkdir creates as 0755. Other local accounts that can traverse the home can read session ids, tags and timings (CWE-276). The gap was already there: pending/<tag> files hold the first line of each prompt's text at 0644, which is more sensitive. Creating the home 0700 would close both.
- [low] signal_cc/adapters/files.py:92 blocks: no. open(path, "a") follows a relay.log symlink planted in the home (probe: the write went through). Only someone who can already write the home can plant one, and `last` and `away` have the same pattern (CWE-59). Not a new trust path.
- [low] .github/ISSUE_TEMPLATE/relay-failure.md:13 blocks: no. A pasted line publicly shows the Claude Code session UUID, the 4-hex tag, the prompt kind, UTC times and seconds waited. Together these show when the owner was away and how often. None of it is a credential or contact detail, and the template says to check before pasting. Hashing or dropping `session` in pasted lines would reduce what a paste reveals (CWE-359).
- [low] blocks: no. Secret scan unmeasured: the repo's CI (tests.yml) runs only unittest and has no secret, dependency or static-analysis step, and none is installed here (gitleaks, trufflehog and detect-secrets are all absent). I ran a manual grep of the added lines for phone numbers, tokens and keys instead, and it found none.

## Probes
- Head confirmed with `git ls-remote origin feat/relay-log` = b2c4f84. I read the item with `wuwei plan show relay-log`, the arch and quality verdicts at 5e1a578, and `git diff origin/main...b2c4f84` (12 files, +291/-22).
- Merge check: the +/- lines of `git diff origin/main...5e1a578` and `git diff origin/main b2c4f84` differ only in the conflict lines (README layer row, the wiring import, and `presence(cfg)` in place of `MacPresence(cfg.idle)` in wiring.conversation, plus the test import). In hooks.quiet, main's away-switch logic (UserPromptSubmit, then the WOKEN check, then set_switch(False)) is unchanged apart from `session_id(hook)`. The merge adds no new behaviour.
- Tests on a `git archive b2c4f84` copy: `python3 -m unittest discover -s tests` ran 55 tests, OK (3.14).
- Privacy probe (scratchpad security-relay-log/probe/probe.py, run with `python3 -I` against the archive copy, using a real FileJournal and the fakes). The secret text and number go into the tool input and project name. A send that raises RuntimeError carrying the prompt text and the number gives 6 lines, all valid JSON. Neither the text nor the number appears in them. The outcomes were answered, send failed, answered, error, error and error. Handler lines name permission, permission and unknown, with the errors ValueError, OSError and KeyError. stdout stayed empty.
- Known-positive controls, each in a fresh archive copy. Mutant `str(error)` in place of the type name in cli.failed: the probe finds the text and the number in the log, and test_a_failing_handler_is_logged_and_the_hook_still_exits_quietly fails (3 subtests). Mutant with the HANDLERS guard dropped: the probe finds the text, written through argv as the handler name, and the bogus-hush subtest fails. Both were killed.
- Injection probe: a session id holding `"` and a newline plus a forged `{"kind":"forged"}` stays on one escaped JSON line, and no forged line appears. json.dumps escapes the input (CWE-117 negative).
- Fail closed: FileJournal.record catches OSError and prints only the path and the errno text to stderr. cli.main catches Exception only, so the SystemExit(2) from listen writes no error line. An unwritable relay.log still lets the hook exit 0 (the existing adapter test covers this).
- Supply chain: no new dependency, lockfile, install script or workflow change. The diff imports only `sys` from the stdlib.
- Confidence high: the privacy contract was checked with real file output, and both guards that enforce it were shown to fail loudly under mutation. The open notes are about local file mode and what a paste reveals, not about the promise.

## Residual risk
Any local account that can traverse the home can read the log. This PR doesn't change that, since pending/ already exposes more. Each public paste reveals session ids and away-time patterns, and only the template's warning guards against that.
