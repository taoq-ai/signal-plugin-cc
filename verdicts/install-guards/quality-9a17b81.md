Verdict: FIX
Gate: quality
Item: install-guards
PR: taoq-ai/signal-plugin-cc#4
Head: 9a17b8163109c767b7589412f61d3fe4740dd3e5
Confidence: medium
Breaking: no

## Findings
- [low] tests/test_adapters.py:146 blocks: yes. Failure: no test reaches the `--print` branch of headless(); with `{"-p", "--print"}` reduced to `{"-p"}` all 41 tests still pass, so `claude --print 'x'` (a real print-mode run, headless() True at the head) would start the Stop listener and hang for the wait with a Signal message sent if the long form were ever dropped (requirement: non-interactive run exits at once and sends nothing). Add `("--print", "x")` with an inherited entrypoint to the headless-true test.
- [low] signal_cc/adapters/processes.py:25 blocks: no. The PR's own residual risk is real and measured: ps flattens quoting, so an interactive `claude "explain what -p does"` gives headless() True and that session silently never relays its Stop message (fails quiet, no harm beyond a lost feature; permission and question relays unaffected). Not fixable from ps output; keep as a README/PR note.
- [low] signal_cc/adapters/processes.py:20 blocks: no. ps is run without handling FileNotFoundError (a Linux image without procps raises out of listen); is_relay already has the same dependency, so it is an existing gap. A bundled short flag such as `claude -pc` is read as not headless (limit).
- [low] blocks: no. The live probe ran a plain command Stop hook; the plugin's Stop hook is asyncRewake, which was not measured here, so that CLAUDE_PID reaches an asyncRewake hook the same way is unmeasured.

## Probes
- Tests at head (`python3 -m unittest discover -s tests`, git archive copy): 41 tests OK on Python 3.14.5 and on the macOS system /usr/bin/python3 3.9.6; origin/main: 36 OK. 5 new tests, none skipped. python3.10 not installed locally.
- Live: one real `claude -p 'reply ok'` in a scratch folder with a throwaway Stop hook calling headless() from the head archive: logged headless=true, CLAUDE_PID set (59776, the ps command "claude -p reply ok", also the hook's parent pid), CLAUDE_CODE_ENTRYPOINT=claude-desktop (inherited). The ps path decides correctly where the entrypoint alone would be wrong.
- Direct probes on stub processes: `explain what -p does` as one argument -> True (the accepted residual); `--print x` -> True; `-pc` -> False; `--model opus -- -p` -> True; empty CLAUDE_PID with no entrypoint -> False.
- Mutants (full-tree copies, null mutant passes, 41 OK): guard removed in hooks.listen killed by test_listen_in_a_headless_run_returns_at_once; streaming exclusion removed killed by test_interactive_and_streaming_sessions_are_not (both forms); `--input-format=` form dropped killed; `--input-format X` form dropped killed; entrypoint fallback to False killed by test_without_the_claude_process_the_entrypoint_decides; fallback `sdk-cli`->`cli` killed; `-p` dropped killed (2 tests); env-decides-always killed (3 tests); fcntl guard in relay.py replaced by pass killed in all handlers of test_without_fcntl_every_hook_exits_silently; `pid.isdigit()` dropped killed (permission and listen tests). Survivor: `--print` dropped from the print flag set (the finding above, re-run in a fresh copy: 41 OK).
- Acceptance: scenario 1 covered (returns under 1 s, StubDaemon.calls empty, no listener record); scenario 2 test_listen_wakes_the_session_with_the_reply passes at the head; scenario 3 covered per handler with stdout and stderr empty (subprocess, fcntl set to None in sys.modules); scenario 4 matrix adds 3.9 (tests.yml diff), CI result not re-read here; scenario 5 (claude plugin validate) not run by this gate.
- Test independence: Base.setUp patches os.environ and pops CLAUDE_PID and CLAUDE_CODE_ENTRYPOINT, so a run inside Claude Code does not decide the outcome; stand-in processes are killed in cleanup. The 1 s bound uses a real ps call and measured well under it.
- Simplicity: none to delete. headless() is one function with one caller; the two `--input-format` forms are each pinned by a test; the fcntl guard is a trust-boundary fail-closed exit and stays.

## Residual risk
Detection rests on ps output of the Claude process, so a prompt argument containing the token `-p` silences the Stop relay in an interactive session, and the asyncRewake environment was not measured live.
