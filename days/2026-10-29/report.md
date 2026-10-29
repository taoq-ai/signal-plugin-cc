# WUWEI report 2026-10-29

## Plan
Plan passes: 1. Checkpoints: 0. Done today: 13. Parked today: 0.
Met goals: none.

## Board
Board (what each open item still lacks):
- team seats: orchestration: open PRs with no shepherd seat running
- ps-flake Make the ps-based tests deterministic (taoq-ai/signal-plugin-cc#15) [fixed-date, last event 0h ago]: gates missing at head c3a137d: quality; sentinel-quality running in session 1e1a75bc-691b-4c65-b396-7a42c300af87 [waiting]
- listener-lifetime Signal replies keep reaching a session across its own turns (taoq-ai/signal-plugin-cc#14) [fixed-date, last event 0h ago]: CI not started at d36cc91 [waiting]; required checks not run at d36cc91: test (ubuntu-latest, 3.10), test (ubuntu-latest, 3.14), test (macos-latest, system)
- self-started-shapes Other turns Claude starts on its own keep the Signal listener [fixed-date, last event 0h ago]: awaiting plan approval [waiting]
- release-ci Release PRs run the tests without a close and reopen [fixed-date, last event 1h ago]: no pull request yet
- wake-text Wake text names signal-relay, still matching old listeners [fixed-date, last event 2h ago]: queued: 3 items in progress, WIP limit 4: finish one first [waiting]
- poll-spinner Clear the phone's spinner after a poll vote in Note to Self [fixed-date, last event 0h ago]: queued: 3 items in progress, WIP limit 4: finish one first [waiting]
- leave-digest One digest when the owner leaves with several finished sessions (taoq-ai/signal-plugin-cc#12) [standard, last event 0h ago]: gates missing at head 820ea2e: arch, quality, security

## Merges
- taoq-ai/signal-plugin-cc#11 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#10 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#9 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#8 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#6 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#7 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#5 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#4 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#3 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#2 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#1 merged through WUWEI's check
- taoq-ai/signal-plugin-cc#1 merged with process gaps: 2200 changed lines: split it, or add a Size: <reason> line; no reviewer requested
- taoq-ai/signal-plugin-cc#2 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#3 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#4 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#5 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#7 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#6 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#8 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#9 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#10 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#11 merged with process gaps: no reviewer requested
- taoq-ai/signal-plugin-cc#11 merged with process gaps: no reviewer requested

## Doors
Refused: 25 (questions sent back to the model: 1). Asked the owner (infrastructure): 0. Notes: 1. Stop reminders: 1.
- 10 x a multi-line or unreadable command naming a door program (found: git push) is refused, and a door na
- 2 x a multi-line or unreadable command naming a door program (found: gh pr) is refused, and a door name 
- 2 x the harness's session transcripts (.claude/projects, .codex/sessions) are written only by the harnes
- 1 x a multi-line or unreadable command naming a door program (found: gh repo) is refused, and a door nam
- 1 x the ledger is written only by WUWEI's hooks; it is the audit record. The cache (.wuwei/cache) is wri
- 1 x "breaking: PR #2 (away-switch) changes non-macOS behaviour: prompts stay at the computer until you s
- 1 x taoq-ai/signal-plugin-cc feat/away-switch leaves draft or asks reviewers only once its gates pass at
- 1 x taoq-ai/signal-plugin-cc#2 is not ready to merge:

## Replies
Replies: 0 owed today, 0 closed, 0 open, 0 overdue.

## Owner
Owner prompts: 22.
- goal: approve these goals? I recommend all three. G-1 Public v1 by 2026-11-05: repo public, CI green on main, and a fresh install from the marketplace relays a real permission prompt and a question. G-2 Daily use by 2026-11-19: you run it for 7 days with no crossed reply, no stuck session and no missed prompt, plus the follow-ups (answered-at-Mac notice, plan approval, one digest when you leave, away switch). G-3 Official directory by 2026-11-30: passes `claude plugin validate --profile directory` and is submitted to Anthropic's plugin directory.
- plan: approve this plan? 9 items on 2 goals, about 28 build hours (1 size point = 1 h); the plan is shown above. I recommend Approve: land-status-ci and rewake-probe start first, in parallel. publish-v1 will still ask you before the repo goes public (author email, install name 'signal').
- owner review: taoq-ai/signal-plugin-cc#1 at 0553016. Merge it? Status command + desk, GitHub Actions CI, and the ports-and-adapters layout. Gates: quality PASS, security PASS, arch PASS after one fix round; CI green on 3.10 and 3.14; 36 tests. I recommend merge (squash): every other code item waits on it.
- breaking: taoq-ai/signal-plugin-cc#2 at 94be975: on non-macOS, prompts stay at the computer until you send `away` (before, every prompt went to Signal); bumps the plugin to 0.2.0. Announced at https://github.com/taoq-ai/signal-plugin-cc/pull/2. Proceed?
- breaking: taoq-ai/signal-plugin-cc#2 at db260bb: on non-macOS, prompts stay at the computer until you send `away` (before, every prompt went to Signal); the plugin moves to 0.2.0. Announced at https://github.com/taoq-ai/signal-plugin-cc/pull/2. Proceed?
- owner review: taoq-ai/signal-plugin-cc#2 at db260bb. Merge it?
- owner review: taoq-ai/signal-plugin-cc#3 at b2c4f84. Merge it?
- owner review: taoq-ai/signal-plugin-cc#4 at bcc6071. Merge it?
- one-way: making taoq-ai/signal-plugin-cc public publishes leone.lage@gmail.com on all 13 commits (history is not rewritten). The same email is already public in taoq-ai/wuwei's commits, so nothing new is exposed. I recommend publishing as is.
- one-way: the plugin installs as `signal@signal-plugin-cc`, and the name is hard to change once others install it. A bare 'signal' can read as an official Signal integration, which the plugin directory's policy review may flag. I recommend renaming the plugin to `signal-relay` (install: signal-relay@signal-plugin-cc) before going public.
- plan: approve this plan? 6 items on 2 goals, about 19 build hours (1 size point = 1 h); the plan is shown above. New since your last approval: rename-plugin (the signal-relay rename plus an ADR for your two publish decisions) and config-perms (make the config folder private, from the #3 security review). The other four were already approved.
- breaking: taoq-ai/signal-plugin-cc#5 at 68abb48: plan approval (ExitPlanMode) now goes to Signal while you're away, reversing the README promise that it always stays on the Mac, with no setting to keep it there; a poll vote can put that session into accept-edits mode; the plugin moves to 0.3.0. Announced at https://github.com/taoq-ai/signal-plugin-cc/pull/5. Proceed?
- owner review: taoq-ai/signal-plugin-cc#5 at 68abb48. Merge it?
- owner review: taoq-ai/signal-plugin-cc#7 at bde4349. Merge it?
- owner review: taoq-ai/signal-plugin-cc#6 at 8baf808. Merge it?
- plan: approve this plan? 6 items on 2 goals, about 15 build hours (1 size point = 1 h); the plan is shown above. New: release-please (changelog, tags, plugin.json version; first release v0.3.0, before publish-v1), path-guards (refuse a foreign config home, unsafe session ids, symlinked cleanup), wake-text (wake text says signal-relay, old text still recognised). Already approved: config-perms, publish-v1, leave-digest.
- owner review: taoq-ai/signal-plugin-cc#8 at 80c27a8. Merge it?
- owner review: taoq-ai/signal-plugin-cc#9 at 3945704. Merge it?
- owner review: taoq-ai/signal-plugin-cc#10 at 2b1fc5b. Merge it?
- owner review: taoq-ai/signal-plugin-cc#11 at 06ce521. Merge it?
- plan: approve this plan? 6 items on 2 goals, about 15 build hours (1 size point = 1 h); the plan is shown above. New: listener-lifetime (the bug you found: Signal replies keep reaching a session across its own turns), ps-flake (the flaky ps-based tests, now blocking merges through the required checks), release-ci (release PRs run the tests by themselves).
- plan: approve this plan? Adds poll-spinner (G-2): a short live probe with you watching the phone, trying the receipt as your own Note to Self message, then a receipt for the vote itself; the first that clears the spinner becomes the fix, otherwise the README documents it as a Signal limit. Everything else in the plan is unchanged.

## Seats and gates
Seats: builder 35, lead 1, sentinel-arch 12, sentinel-quality 22, sentinel-security 11, shepherd 1.
Verdicts: arch FIX 5, arch PASS 6, quality FIX 5, quality PASS 15, security FIX 3, security PASS 8.
Verdicts missing after a reminder: 0.

## Telemetry
Tool calls: 1853; outward (MCP) calls: 41.
Top tools: Bash 1582, Write 95, Agent 59, AskUserQuestion 23, mcp__ccd_turn__wrap_up 21, SendMessage 20, Read 16, Edit 14.
Hook errors: 0.

## Learning
- Sample for you this week: taoq-ai/signal-plugin-cc#3 (read its evidence comment)
- gate yield arch: 11 verdicts, 5 FIX (45%)
- gate yield quality: 20 verdicts, 5 FIX (25%)
- gate yield security: 11 verdicts, 3 FIX (27%)
- tokens by role: builder 2466671, lead 211518, sentinel-arch 502244, sentinel-quality 579556, sentinel-security 446157, shepherd 1569
- seat builder claude-opus-5-5 high: 1 launches, 0.0 fix rounds per item, 0 blocking findings, 0 escapes, 113767 tokens
- seat builder claude-opus-5-5 medium: 10 launches, 0.0 fix rounds per item, 0 blocking findings, 0 escapes, 799995 tokens
- seat builder claude-sonnet-5-5 medium: 3 launches, 0.0 fix rounds per item, 0 blocking findings, 0 escapes, 63235 tokens
- seat lead claude-opus-5-5 xhigh: 1 launches, 0.0 fix rounds per item, 0 blocking findings, 0 escapes, 211518 tokens
- seat sentinel-arch claude-opus-5-5 high: 11 launches, 0.6 fix rounds per item, 8 blocking findings, 0 escapes, 426964 tokens
- seat sentinel-quality claude-sonnet-5-5 high: 21 launches, 0.6 fix rounds per item, 10 blocking findings, 0 escapes, 508559 tokens
- seat sentinel-security claude-opus-5-5 high: 11 launches, 0.2 fix rounds per item, 3 blocking findings, 0 escapes, 446157 tokens
- seat shepherd claude-sonnet-5-5 medium: 1 launches, 0.0 fix rounds per item, 0 blocking findings, 0 escapes, 1569 tokens

Ledger: intact
