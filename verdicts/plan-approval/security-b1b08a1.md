Verdict: PASS
Gate: security
Item: plan-approval
PR: taoq-ai/signal-plugin-cc#5
Head: b1b08a139725cf596fa6ed54948068f5054e17d8
Confidence: medium

## Findings
- [low] signal_cc/domain/forms.py:124 blocks: no. The mutant `len(reply.votes) < 1` survives the suite. On that mutant, a vote of optionIndexes [1, 2] on the single-choice poll picks auto-accept, and the head refuses it as unreadable (probe). Signal clients send one index for a noMulti poll, so only a non-standard client could reach this. Note: add a case such as `Reply("", 102, [1, 2]) -> None` (CWE-1287).
- [low] signal_cc/app/conversation.py:83 blocks: no. A pollVote with no targetSentTimestamp, sent while the plan is the only prompt waiting and the latest message, reaches PlanForm.parse with target None. That call returns the auto-accept decision, and then `form.polls[None]` raises TypeError. cli.main catches the error, so the prompt falls back to the Mac (fails closed by accident). signal-cli always sets targetSentTimestamp, so this is not reachable from a real client. Note: return None for votes when target is None.
- [low] signal_cc/entry/hooks.py:22 blocks: no. The mutant `if False:` for the AskUserQuestion skip survives. No test pins that AskUserQuestion stays out of the PermissionRequest relay (the base had no test either).
- [low] blocks: no. README Security says auto-accept means "its file edits stop asking". The probe the plan cites covered only Write and Edit. Whether this Claude Code version's acceptEdits mode also accepts filesystem Bash commands (mkdir, mv and similar) was not measured. If it does, the README understates what the vote unlocks.
- [low] blocks: no. A plan with no `plan` field goes out as "Plan from <proj>:" followed by an empty body, and the owner can still approve it. It would be clearer to send "(no plan text)" in that case.
- [low] blocks: no. Scanner: the repository has no secret, dependency or SAST step (CI runs only unittest), so this is unmeasured. The diff adds no dependency or workflow.

## Probes
- Tests at the head, in a git archive copy: `python3 -m unittest discover -s tests` ran 41 tests, OK.
- Routing probe (FakeMessenger, real Conversation and route, PlanForm). Outcomes:
  - Vote [1] on this prompt's poll: allow with setMode acceptEdits, destination session.
  - Vote [1] on another session's poll ts: no decision (SKIP).
  - Vote [1] on a stale poll ts: no decision.
  - Thumbs-up on another session's message: no decision.
  - Plain "y" while another prompt waits: no decision (hint or skip).
  - "0fff y" tagged for the other prompt: no decision.
  - Text "0001 2": deny with feedback, no auto.
  - Text equal to the "Approve, auto-accept edits" label: deny with feedback, no auto.
  - Plain "y" as the only waiting prompt: allow without updatedPermissions.
  - Votes [1, 2]: unreadable, no decision.
  - Conclusion: auto-accept is reachable only through a single-index vote whose target is this prompt's own poll timestamp. Text and reactions never reach it.
- Owner gate: signal_cli.parse_event drops every envelope whose source is not cfg.owner. This diff leaves it unchanged.
- Scope: the only setMode in the tree is `{"mode": "acceptEdits", "destination": "session"}`. grep finds no bypassPermissions, userSettings or localSettings. Mutating the destination to userSettings is killed by test_plan_form_reads_votes_reactions_and_feedback.
- Fail closed:
  - At the Mac, ask returns None and nothing is sent (test_at_the_mac_nothing_is_sent covers PlanForm).
  - On timeout or return to the Mac the result is None, and the Mac dialog shows.
  - An exception goes to cli.main's catch-all, which prints no decision.
- Secrets: the Signal text carries the project basename and tool_input.plan only. planFilePath is not sent (probe). The registry stores only the first line, "Plan from <proj>:". updatedInput echoes tool_input back to Claude Code only. Owner feedback reaches Claude only as a deny message.
- 1500 cut:
  - 1500 characters: no note. 1501 and 5000 characters: "(first 1500 of N characters)" is appended.
  - Total text is at most 1644 characters, so it stays one Signal message.
  - The poll is still sent after the cut (test_a_long_plan_is_cut_with_its_length_noted).
  - Text the plan hides past 1500 characters is always disclosed by the length note.
- Mutants, each in its own copy of the head:
  - Killed: auto always; choice<2 to <=2; y to auto; updatedInput dropped; destination userSettings; plan routed to PermissionForm; length note removed; range guard removed; n to approve; feedback to approve.
  - Surviving, both re-run in a fresh copy: M1 (`len < 1`) and M7 (AskUserQuestion skip). Both are noted above.
- Differential: decide() at base vs head over 19 inputs (y/n words, case, skin tones, FE0F, empty, free text) gives 0 differences. The `word()` extraction is behaviour-preserving.
- Supply chain: no new dependency, lockfile, install script or workflow change.
- Confidence is medium because I did not re-run the Claude Code runtime behaviour (allow needs updatedInput; setMode session gives acceptEdits). It rests on the probe recorded in the plan item.

## Residual risk
A vote for auto-accept leaves the session in acceptEdits until the mode changes, even after the owner is back at the Mac. The README says so. Anyone who can send as the owner number can pick it, which is the existing trust boundary.
