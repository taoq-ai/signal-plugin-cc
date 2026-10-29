Verdict: PASS
Gate: quality
Item: path-guards
PR: taoq-ai/signal-plugin-cc#11
Head: 06ce5218a734e4f0e118824d2a22be9cd281b136
Confidence: medium
Breaking: no

## Findings
- [low] signal_cc/entry/cli.py:36 blocks: no. A symlinked listeners/ makes private.remove raise OSError, and the existing `except OSError` prints it as "signal-cli daemon on port N: [Errno 20] Not a directory: .../listeners". Nothing outside the home is deleted and the exit is 0, but the message names the daemon, not the symlink. A wording note for the PR's review notes.
- [low] signal_cc/adapters/files.py:36 blocks: no. FileRegistry.release (pending/<tag>) and AwaySwitch.set(False) still unlink by path. Neither takes a session id: the tag comes from claim(), which already refuses a symlinked pending/, and away sits directly in the home. Not part of this promise.

## Probes
Tests: `python3 -m unittest discover -s tests` on git archive copies. Head 06ce521: 91 tests, OK on 3.14.5 and on /usr/bin/python3 3.9.6. origin/main 86d57a1: 85 tests, OK on both. +6 tests, all in PathGuardTest. None skipped (the run prints no skip count). 3.10 was not available locally; CI covers it.
Mutants, each a full-tree copy of the head run on the whole suite. The null mutant passed 91/91.
- session_id regex loosened to `.+`: killed by 14 failures (test_a_session_id_that_is_not_a_plain_token_is_refused, test_listen_and_quiet_never_touch_a_file_outside_the_home).
- isinstance(str) check removed: killed (bad=7 and bad=None error).
- wiring.home call removed in cli.main: killed by test_a_home_another_account_owns_is_refused_by_every_hook, all 6 handlers.
- `return` after the home refusal removed: killed by the same test, 6 failures.
- uid check disabled in private.home: killed by 8 failures (the six handlers, test_private_home_refuses_a_foreign_owner, and the parent test).
- `except hooks.Refused` branch disabled: killed by 6 failures. The generic handler prints a traceback and fails the one-stderr-line assertion.
- Files.clear reverted to path.unlink: killed by test_quiet_never_deletes_through_a_symlinked_listeners_folder.
- O_NOFOLLOW dropped in private.remove: killed by the same test.
- Not mutated: the chmod tightening in private.home is pre-existing and covered by PrivateHomeTest.
Acceptance through cli.main (standalone script on temporary homes, stdin faked, Popen patched):
- Session ids `../../escape`, an absolute path, `..` and `a/b`, for both listen and quiet: each gave return None, empty stdout, and one stderr line. Nothing was written under the home or outside it.
- listeners/ symlinked to an outside folder holding s1.pid: quiet printed one stderr line and returned; the outside file still existed.
- Foreign home: covered by test_a_home_another_account_owns_is_refused_by_every_hook (uid faked via Path.stat). That test checks stdout empty, one stderr line, the tree unchanged, mode not tightened, and no daemon call.
- A real uuid4 session id via quiet: no stderr, no stdout. The home holds only config.json and relay.log. The tests also assert a UUID-shaped id passes, plus `unknown`, and a missing id gives "unknown".
Test quality: the tests assert on file trees, return values and the journal's error type. The one prose assertion (assertIn "session_id", "another account") is secondary to the tree and exit checks. No wall-clock, network or shared-file dependence beyond the existing in-process StubDaemon; config sets wait/listen to 1 so a failed guard stays bounded.
Order of calls: in listen and quiet, session_id is evaluated before any write. If private.remove raises on a symlinked folder, processes.stop is never reached, so a pid read through the symlink is not signalled.
Simplicity: none to delete. wiring.home is a one-line pass-through to private.home, kept so the entry layer does not import adapters directly (matches the ports-and-adapters layout). Trust-boundary checks stay.

## Residual risk
A race between the folder check and the unlink is closed by the directory handle; the guard on the home's owner is a one-time check at hook start, and the daemon and desk subprocesses re-check it through private.home on their own writes. The foreign-uid test fakes the owner rather than using a real second account.
