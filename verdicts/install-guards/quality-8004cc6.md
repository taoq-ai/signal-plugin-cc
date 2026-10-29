Verdict: PASS
Gate: quality
Item: install-guards
PR: taoq-ai/signal-plugin-cc#4
Head: 8004cc6d72e7bd9bd474a9af0533d695b2c373a5
Confidence: high
Breaking: no

## Findings
- [low] signal_cc/adapters/processes.py:25 blocks: no. Carried note: ps flattens quoting, so an interactive `claude "explain what -p does"` reads as headless and that session never relays its Stop message (fails quiet; permission and question relays unaffected); not fixable from ps output, keep as a README/PR note.
- [low] blocks: no. Carried note: a bundled short flag such as `claude -pc` reads as not headless, and the asyncRewake Stop hook's CLAUDE_PID was not measured live (the live probe used a plain command hook).

## Probes
- closed: no test reaches the `--print` branch (my FIX at 9a17b81) at 8004cc6; the print-mode test now loops over `("-p", "reply ok")` and `("--print", "x")` with an inherited `claude-desktop` entrypoint.
- Tests at head (`python3 -m unittest discover -s tests`, git archive copy): 43 OK on Python 3.14.5 and on /usr/bin/python3 3.9.6; the delta adds 2 tests, none skipped. CI at the same head: test (3.14) ran 43 OK; test (3.9) fails at setup-python (3.9 not available for Ubuntu 26.04, the known runner issue); test (3.10) was cancelled by that failure, not run.
- Mutants (full-tree git archive copies, null mutant 43 OK on both Pythons):
  - `{"-p", "--print"}` reduced to `{"-p"}`: killed by test_print_mode_is_headless_even_with_an_inherited_entrypoint (args=('--print', 'x')), on 3.14 and 3.9.
  - `pid.isdigit()` replaced by `pid`: killed by test_only_a_single_pid_is_read, on 3.14 and 3.9.
  - `except OSError` replaced by `except ZeroDivisionError` (ps missing escapes): killed by test_without_ps_the_entrypoint_decides, both subtests, on 3.14 and 3.9.
- Test independence: test_without_ps sets PATH to empty inside Base's patched environment (restored by the base class); test_only_a_single_pid reads a real stand-in process, no network or shared file.
- Previously killed mutants (guard in hooks.listen, streaming exclusion, both `--input-format` forms, entrypoint fallback, fcntl guard) sit in code the delta did not touch.
- Simplicity: none to delete. The OSError catch is fail-closed handling (falls back to the entrypoint) and stays; the isdigit check is trust-boundary input validation and stays.

## Residual risk
Detection rests on ps output of the Claude process, so a prompt argument containing the token `-p` silences the Stop relay in an interactive session; the Python 3.10 CI leg has not run at this head because the 3.9 setup failure cancelled it.
