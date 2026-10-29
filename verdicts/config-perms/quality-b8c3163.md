Verdict: FIX
Gate: quality
Item: config-perms
PR: taoq-ai/signal-plugin-cc#8
Head: b8c316325db56be1ec6e2d1e9e7b466b7f32c2a3
Confidence: medium
Breaking: no

## Findings
- [medium] signal_cc/adapters/private.py:5 blocks: yes. Failure: dropping the "w": os.O_TRUNC flag from FLAGS leaves all 66 tests green; Listeners.set("s", 12345) then Listeners.set("s", 7) leaves the pid file reading '72345', so Listeners.get returns a pid that is not the listener and stop()/clear() act on the wrong process (requirement: private.open_file must keep the truncating "w" semantics the old write_text had; the flag mapping is new code with no test)
- [medium] signal_cc/adapters/private.py:5 blocks: yes. Failure: dropping the "a": os.O_APPEND flag from FLAGS leaves all 66 tests green; with it gone every FileJournal.record and daemon.log/relay.log open ("a"/"ab") writes at offset 0 and overwrites the earlier entries instead of appending (a second shorter record garbles the first line), so concurrent sessions lose relay outcomes (requirement: relay.log appends one line per outcome; no test records twice)
- [low] signal_cc/adapters/files.py:119 blocks: no. Listeners.set uses private.folder(self.dir), but the symlink test plants only a symlinked file inside a real listeners/ dir; mutant "listeners no folder()" (plain mkdir exist_ok) survives, so a symlinked listeners/ dir is untested. Add listeners -> outside dir to that test.
- [low] signal_cc/adapters/processes.py:44 blocks: no. Mutants "spawn no home" and "daemon no home" (plain mkdir parents) survive: write_everything has the journal create the home first, so spawn() and SignalCli.start() on a fresh home are untested for the 0700 home. Create the home through each alone in a test.
- [low] signal_cc/adapters/private.py:12 blocks: no. Mutant "no uid check" survives (home owned by another user is untestable without a second account); and the mutant mkdir(mode=0o755) survives because the chmod tightens it straight after, so the mode argument only closes the short window before the chmod. Neither is a defect.
- [low] blocks: no. Existing files in an existing home keep their mode (probe: a 0644 relay.log stays 0644 after FileJournal.record); only the 0700 home protects them, which meets the promise ("tightens an existing home") but a pre-existing pending/ or listeners/ dir stays 0755 behind it. A limit, not a regression.
- [low] blocks: no. Linux O_NOFOLLOW behaviour is unmeasured here (macOS only, no Linux host). CI runs 3.10 on Linux, which will exercise the new tests. On macOS a dangling symlink opened with w, a or x all fail (ELOOP, ELOOP, EEXIST) and the target is never created.

## Probes
- Tests on `git archive` copies, HOME pointed at a missing scratch dir (never created, so nothing in the real home or ~/.config/signal-plugin-cc was touched): head b8c3163 66 tests OK on python 3.14.5 and on /usr/bin/python3 3.9.6; origin/main base c7d7222 62 tests OK on both. 3.10 not installed, not run. Skips: none in the output (Ran 66, OK). The merge with the moved main (9947c90) is clean (git merge-tree, tree 3505790); tests not re-run on the merged tree.
- Mutants (full tree copy, 3.14, real counts, 26 run): null mutant passes (rc 0). Killed: no chmod tighten and tighten-any-mode (test_an_existing_home_left_open_is_tightened); folder mkdir 0755, file 0644, desk-lock/away/mark_latest/spawn/daemon/listeners-set/claim-file plain open, claim no folder(), claim no home() (fresh-home test); folder follows symlink, no O_NOFOLLOW (symlink tests, the hook test included); no O_EXCL (test_claims_never_reuse_a_waiting_tag_and_expire); journal no home() (open-home test). Survived: home mkdir 0755 (equivalent given the chmod), no uid check, no O_TRUNC, no O_APPEND, x not mapped to w (equivalent: fdopen accepts "x"), listeners no folder(), spawn no home, daemon no home. Only O_TRUNC and O_APPEND have a named failing input (above), reproduced in a fresh copy: pid '72345' and a garbled log.
- Every file the relay writes is created 0600: the fresh-home test covers relay.log, last, away, pending/<tag>, listeners/s1.pid, desk.lock, daemon.log with umask 022, home 0700 and folders 0700. My probe repeats it at umask 000 and finds no bad mode.
- Concurrent first creation: 64 jobs on 16 processes (spawn start method) each journaling, claiming, marking last, setting away and a listener under the same fresh nested home at umask 000: 0 errors, 133 entries, no mode outside 0700/0600, home 0700, 64 relay.log lines. Same result on 3.14 and 3.9.
- Other probes (both pythons): an own 0777 home is tightened to 0700; a symlinked home dir has its target tightened (own dir only, not a threat); acceptance 2 (symlink at relay.log, hook exits 0, stdout empty, target untouched, a stderr line names relay.log) is covered by the subprocess test, which passes.
- Test hygiene: new tests use tempfile / self.home temp homes, set and restore umask, no network beyond the existing StubDaemon on 127.0.0.1; no wall-clock dependence; processes.Popen and signal_cli.Popen are mocked. The 0600 assertion is on modes, the symlink assertion on target content: decisions, not prose.
- Defects seen before: no error path here ends a long job on a temporary failure (journal still prints to stderr and continues; hook exits 0).
- Simplicity: private.py is 29 lines and replaces ten mkdir/open sites; nothing to delete. The FLAGS table and fdopen mapping can stay but need the two tests above. folder() symlink refusal and the O_NOFOLLOW open are trust-boundary guards, not deletable.
- Fix needed: one test that writes twice through FileJournal (and AwaySwitch/last if wanted) and reads back both lines, and one that sets a longer then a shorter pid and reads the shorter. Then both mutants die.

## Residual risk
Linux O_NOFOLLOW is unmeasured locally; the two flag-mapping tests are missing, but the head behaves correctly under every probe I ran.
