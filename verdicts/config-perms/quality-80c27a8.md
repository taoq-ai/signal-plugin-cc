Verdict: PASS
Gate: quality
Item: config-perms
PR: taoq-ai/signal-plugin-cc#8
Head: 80c27a87e888d3e421be67d2f790c8ef53cc7d35
Confidence: high
Breaking: no

## Findings
- [low] signal_cc/adapters/private.py:12 blocks: no. The "no uid check" mutant (home owned by another user) and the mkdir(mode=0o755) mutant (the chmod tightens it straight after) stay untested; neither has a failing input, so neither is a defect.
- [low] blocks: no. Existing files in an existing home keep their mode (a 0644 relay.log stays 0644); only the 0700 home protects them. A limit that meets the promise "tightens an existing home", not a regression.
- [low] blocks: no. Linux O_NOFOLLOW behaviour is unmeasured here (macOS only). CI on Linux runs the symlink tests (run 40923094211, as the brief reports; I did not re-read it).

## Probes
- closed: no O_TRUNC finding at 80c27a8 (killed by test_a_shorter_pid_or_tag_replaces_a_longer_one_whole).
- closed: no O_APPEND finding at 80c27a8 (killed by test_sessions_appending_at_once_keep_every_line).
- closed: listeners no folder() at 80c27a8 (killed by test_a_symlinked_listeners_folder_is_not_written_through and the fresh-home test).
- closed: spawn no home and daemon no home at 80c27a8 (each killed alone by test_the_daemon_log_alone_creates_a_private_home).
- Baseline on a `git archive 80c27a8` copy of the full tree, HOME pointed at a never-created scratch dir: 83 tests OK on python 3.14 and on /usr/bin/python3 (3.9.6); no skips in the output. The scratch HOME stayed empty afterwards, so nothing touched a real home, ~/.config/signal-plugin-cc, port 8299 or Signal.
- Mutants, full tree copy, 3.14, real counts, 9 run. Null mutant: rc 0, 83 OK. Killed: no O_TRUNC, no O_APPEND, no O_EXCL (test_claims_never_reuse_a_waiting_tag_and_expire), no O_NOFOLLOW (planted-symlink hook test and test_no_write_follows_a_symlink_planted_in_the_home), listeners no folder(), spawn no home, daemon no home, no chmod tighten (test_an_existing_home_left_open_is_tightened). 0 survivors among them. The two blocking mutants of b8c3163 both die.
- Write audit after the merges (grep over signal_cc, relay.py, hooks for open, write_text, write_bytes, mkdir, makedirs, os.open, fdopen, chmod, touch, mkstemp, rename): every create or write is in files.py (lines 33, 64, 81, 96, 120, 138), signal_cli.py:28 and processes.py:48, each via private.open_file/home/folder. The only direct mkdir and chmod are inside private.py. config.py only reads. #5, #7 and #6 added no file write; processes.stop(pid, why) only calls os.kill.
- Test hygiene: the new tests use self.home temp dirs and mock Popen in processes and signal_cli; no wall-clock, network or shared-file dependence. The append test holds two handles open and writes alternately, so it checks the flag, not timing. Assertions are on modes, file content and target content.
- Defects seen before: no error path here ends a long job on a temporary failure (the journal prints to stderr and continues; the hook exits 0).
- Simplicity: none to delete. private.py is 29 lines and replaces the ten mkdir/open sites. folder()'s symlink refusal and the O_NOFOLLOW open are trust-boundary guards.

## Residual risk
Linux O_NOFOLLOW is unmeasured locally and rests on CI. The other-owner home path (uid check) cannot be tested without a second account.
