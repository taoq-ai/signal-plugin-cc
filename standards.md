# Standards

## Builder
- Push in its own one-line call; keep the PR body in a file and pass the whole file on every edit, with any `No test:` line unbulleted at the start of a line and the WUWEI footer as the last line. A branch behind main gets a normal merge of origin/main, never a rebase or force push. (2026-10-29: 11 refused pushes; footer dropped on #2 to #5; a bulleted `No test:` WUWEI could not read; two briefs asked for a force push.)
- A planner brief for a branch that fell behind main asks for a merge of origin/main, not a rebase. (2026-10-29)

## Gates
- Arch: a hook handler that treats every UserPromptSubmit, Stop or SessionEnd as typed input is a finding; whether an event fires for turns Claude Code starts itself is settled with a hook input captured live on the owner's Claude Code version, not a static read. (2026-10-29: the listener bug from 402eecb survived #2's gate; the owner found it live.)
- Quality: a process-lifetime or hook scenario covered only by a fake gets one test against the real file adapter with the writer process exited; a ps- or timing-based test passes 50 serial runs. (2026-10-29: leave-digest gone entries passed 108 tests with a pid-less fake; the ps flake on main.)
- Quality: a workflow that opens PRs with GITHUB_TOKEN does not run the required checks on them; the item says how those PRs get CI. (2026-10-29: release PR #10 needed a close and reopen.)
- Verdict Head is the full 40-character sha.

## Planner
- Ask the owner one question per AskUserQuestion call; batched questions were not recorded (answer.unconfirmed). (2026-10-29)
- Live tests of the relay rely on the Mac's idle time: a prompt typed into a session counts as the owner at the Mac and turns away off. (2026-10-29, publish-v1)
