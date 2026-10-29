Verdict: PASS
Gate: quality
Item: plan-approval
PR: taoq-ai/signal-plugin-cc#5
Head: b1b08a139725cf596fa6ed54948068f5054e17d8
Confidence: medium
Breaking: no

## Findings
- [low] tests/test_domain.py:0 blocks: no. Untested: reversing `len(reply.votes) != 1` to `< 1` in PlanForm.parse survives; a two-option vote on this single-choice poll would approve option 1. Signal does not allow it on a single-choice poll, so no concrete input reaches it. A [0, 1] case would pin it.
- [low] tests/test_domain.py:0 blocks: no. Untested: the plan-length boundary (`>` to `>=` survives; a plan of exactly 1500 characters would get a "first 1500 of 1500" note) and `.strip()` on the plan text (removal survives). Cosmetic only.
- [low] signal_cc/entry/hooks.py:22 blocks: no. Untested: the rewritten `if tool == "AskUserQuestion": return None` skip survives its removal. The same gap exists on origin/main, where emptying NOT_RELAYED also passes 36 of 36 tests. The diff keeps the behaviour, so it is a pre-existing gap and a new test would help.
- [low] signal_cc/entry/hooks.py:12 blocks: no. Three blank lines before `def project` (a leftover of the removed NOT_RELAYED line); CI runs no linter.

## Probes
- Tests on `git archive` copies. Head: 41 tests, OK on Python 3.14.5 and /usr/bin/python3 3.9.6. origin/main (55f491f): 36 tests, OK on both. The 5 added tests are all collected and none are skipped.
- Approval paths: every approve goes through PlanForm._approve and carries `updatedInput` (the original tool_input). Only `choice == 1` (the poll's auto-accept option) adds `updatedPermissions` setMode acceptEdits (session). Thumbs-up with a skin tone, `y`, `yes` and `ok`, and poll option 1, return allow with updatedInput and no setMode. This matches the run evidence from Claude Code 2.1.311. The tests assert the exact decision dicts, including the end-to-end hook JSON for a reaction.
- Unreadable or ambiguous replies never approve. These all return None or deny: an empty text, an empty vote list, an out-of-range vote, a vote on option 3, and free text including a quoted "add a migration step". None sets updatedInput.
- Mutants run in full-tree copies of the head with a passing baseline; the null mutant passed (rc=0). 25 mutants in all.
- Killed, with the failing test named:
  - drop updatedInput: test_a_plan_is_approved_with_its_input and test_plan_form_reads_votes_reactions_and_feedback.
  - setMode always on: both of those tests again.
  - setMode on option 0: test_plan_form_reads_votes_reactions_and_feedback.
  - `choice < 3` (option 2 approves): test_plan_form_reads_votes_reactions_and_feedback, the [2] case.
  - range+1: the [3] case.
  - len guard removed: the [] case.
  - empty text approves or guard removed: the Reply("") case.
  - YES list emptied: the reaction test.
  - NO branch removed: import errors across the suite.
  - unknown text approves: the feedback tests.
  - skin tones left in: test_decide.
  - no cut: test_a_long_plan_is_cut_with_its_length_noted.
  - no length note: the same test.
  - no poll: test_plan_feedback_end_to_end.
  - receipt mutants: test_plan_form_reads_votes_reactions_and_feedback.
  - hook routes ExitPlanMode to PermissionForm: the two adapter plan tests.
  - hook skips ExitPlanMode: the same two.
  - decide inverted: 5 failures.
- Survivors, as the three low notes above: `len < 1`, `limit >=`, no strip, and the AskUserQuestion skip removed. Each was re-run once against the head copy and gave rc=0.
- At-the-Mac: test_at_the_mac_nothing_is_sent now covers PlanForm, and `ask` returns before any send. The item's six acceptance scenarios each map to a test.
- Not run: no Signal send, no port 8299, no ~/.config/signal-plugin-cc. The probe of Claude Code itself is read from the plan item's run evidence, not rerun.
- Simplicity: PlanForm.parse repeats decide()'s YES and NO matching, but the tables are shared through the new `word()`, so the duplication is small. The reply matching could be unified with decide() later; nothing needs deleting now. `texts.py` is left untouched, which is right.

## Residual risk
Real Claude Code behaviour after allow rests on the probe at 2.1.311; a later version that stops honouring updatedInput would leave the plan dialog open on the Mac, with no data loss. The README Security text says what is relayed.
