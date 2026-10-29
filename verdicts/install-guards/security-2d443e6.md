Verdict: PASS
Gate: security
Item: install-guards
PR: taoq-ai/signal-plugin-cc#4
Head: 2d443e65594a35cda78102988c98a5d3e995c400
Confidence: medium

## Findings
- [low] signal_cc/adapters/processes.py:33 blocks: no. Carried over from 9a17b81: the argv check splits ps output on whitespace, so prompt text counts as flags (a prompt holding --input-format=stream-json, or an interactive run whose prompt holds " -p "), and combined short flags (-cp) are not recognised. A miss restores base behaviour, and the same user controls the inputs (CWE-807, limit).
- [low] signal_cc/adapters/processes.py:23 blocks: no. subprocess.run(ps) still has no timeout, the same as the existing is_relay.
- [low] signal_cc/entry/hooks.py:45 blocks: no. Comes from main (#2), not this PR: a claude -p run still fires UserPromptSubmit, so quiet() turns the away switch off. An automated headless run started while the owner is away therefore sends later prompts back to the Mac when it is in use. This fails toward the Mac (availability, not exposure).
- [low] blocks: no. The repository and its CI have no secret, dependency or static-analysis scanner, so that coverage is unmeasured, not clean. Actions stay pinned to major tags (checkout@v4, setup-python@v5), as on base.

## Probes
- PR #4 read once: head 2d443e6, draft, base main. Three checks were SUCCESS: ubuntu 3.10, ubuntu 3.14 and macos system.
- Delta read: 9a17b81..8004cc6 (processes.py and tests), 8004cc6..e9cd67b (workflow) and fbc44e1..2d443e6 (what the PR adds over main after the merge). Over main, the PR adds only relay.py, processes.headless, the listen guard, plugin.json homepage and repository, README, the workflow and tests.
- Merge: in listen(), `if processes.headless(): return None` comes before quiet() and before the listener pid is recorded. From main, the away switch (AwaySwitch, MacPresence.switch, desk away/back, quiet's WOKEN check, wiring.presence) is intact and matches fbc44e1. The quiet() call inside listen passes a Stop event, so it does not reset the switch.
- Workflow: it triggers on push to main and on pull_request (not pull_request_target), with top-level permissions contents: read. The matrix is three static include rows, so no untrusted expression reaches run. The macOS leg runs /usr/bin/python3 with no setup-python. No new action or dependency.
- Tests: `python3 -m unittest discover -s tests` on a git archive copy with HOME set to scratch ran 49, OK on Python 3.14. The same suite under /usr/bin/python3 (3.9.6) also ran 49, OK.
- Mutants, each in a fresh archive copy. isdigit changed to a truthy check: test_only_a_single_pid_is_read fails. `except OSError` changed to ValueError: test_without_ps_the_entrypoint_decides errors (2). Listen guard removed: test_listen_in_a_headless_run_returns_at_once fails. {"-p","--print"} changed to {"-p"}: test_print_mode_is_headless_even_with_an_inherited_entrypoint fails (--print subtest). None survive.
- No-ps probe: relay.py listen under env -i with PATH=/nonexistent, CLAUDE_PID=123, CLAUDE_CODE_ENTRYPOINT=sdk-cli and a scratch SIGNAL_CC_HOME (port 1) gave rc 0, empty stdout and stderr, and no listener file.
- closed: isdigit guard untested (processes.py:22) at 8004cc6
- closed: missing ps gave a misleading daemon-port error (cli.py:21) at 8004cc6
- Confidence is medium, unchanged from 9a17b81. CLAUDE_PID was not observed in a real hook environment, and Linux procps width truncation of `ps -o command=` was not measured.

## Residual risk
The guard trusts process argv and environment that the same user controls, and a miss restores the base Stop listener. The merged away switch is a file under the config home that any local process of the user can toggle, which is the same trust level as the config.
