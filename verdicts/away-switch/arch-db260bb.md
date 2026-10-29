Verdict: PASS
Gate: arch
Item: away-switch
PR: taoq-ai/signal-plugin-cc#2
Head: db260bbce8ea67c622b2eb2e0e7ce8d019bbc477
Confidence: medium
Breaking: yes: on non-macOS hosts, and on a Mac whose idle time can't be read, the README at base 55f491f documented "every prompt goes to Signal first"; from this head nothing goes to Signal there until the owner sends away. Announced (Announcement line in the PR body, README Limits names 0.2.0), owner-confirmed breaking: at 94be975, plugin.json 0.1.0 to 0.2.0.

## Findings
- [medium] PR-body:0 blocks: no. The Assumptions line says other self-started turns (a /loop or scheduled task, a background subagent's report, a message from another session) "fail safe: idle time decides again, as it did before this PR". That holds on a Mac only. On a host without idle time, the switch is the only route to Signal: an owner who sent away and left a background subagent running stops getting prompts when it reports, and nothing tells them. The promise defines the off trigger as UserPromptSubmit and the hook input has no source field, so this is a platform limit, not a violated requirement. The assumption text should say so for non-macOS. A cheap widening is to also leave the switch on when the prompt starts with the <task-notification> wrapper the builder's own test uses, which covers subagent, shell and monitor notifications; /loop prompts stay indistinguishable.
- [low] signal_cc/entry/hooks.py:45 blocks: no. processes.stop now runs before set_switch. If the listener exits between is_relay and os.kill, ProcessLookupError skips the switch change for that typed prompt. The window is tiny and the next typed prompt fixes it. A try/finally around the stop closes it.

## Probes
- closed: high hooks.py:40 (asyncRewake wake turns the switch off) at db260bb. quiet() skips set_switch when the prompt contains WOKEN, and listen() prints WOKEN on stderr as the first line before exit 2. The plugin's own wake is the turn that follows every Signal reply, so this is the main path. Other self-started turns stay as the note above.
- Binary (local Claude Code 2.1.312, read statically from `strings`, nothing run): the asyncRewake handler `_tt` on exit 2 builds the body as `${rewakeMessage ?? 'Stop hook blocking error from command "<name>":'} ${stderr || stdout}`. It runs it through zC and tWe, which only neutralise a trailing `<` and a list of XML tag names, and enqueues it with ran() as a mode "task-notification" value. plugin hooks.json sets no rewakeMessage. WOKEN is plain ASCII with no tag characters and comes right after the prefix, so it reaches the queued prompt text intact. Not confirmed at runtime that the UserPromptSubmit `prompt` field equals that value: no live session was woken. That is why confidence is medium.
- The builder's rejection of the "Mac input in the last RETURNED seconds" alternative holds: without idle time, a typed prompt would never turn the switch off. Recorded under Assumptions.
- closed: low macos.py:29 (unknown idle on a Mac) at db260bb: README Limits now says the same holds on a Mac whose idle time can't be read.
- closed: low hooks.py:41 (set_switch before stop) at db260bb: quiet() stops the listener first.
- closed: low PR-body (no Announcement) at db260bb: `Announcement: https://github.com/taoq-ai/signal-plugin-cc/pull/2` present; owner confirmed breaking: at 94be975.
- Tests: `git archive db260bb` into a fresh scratch folder, then `HOME=<scratch>/home python3 -m unittest discover -s tests`: 42 tests OK. This includes tests/test_architecture.py (inward-only layers, wiring alone picks adapters). The delta adds no import, so it adds no cycle or layering change. WOKEN lives in entry/hooks.py beside both its producer (listen) and its consumer (quiet).
- Mutants, each in a fresh archive copy, all killed: drop `and WOKEN not in prompt` (test_a_turn_woken_from_signal_leaves_the_switch_on fails); WOKEN check forced False (typed-prompt test fails); listen() prints a different wake line (woken test fails, so producer and consumer are tied by a test); drop the UserPromptSubmit check (2 fail).
- Contracts: the delta touches only entry/hooks.py (quiet, listen), plugin.json version, README Limits and one test. The hooks.json wiring is unchanged (quiet on UserPromptSubmit and SessionEnd, listen on Stop with asyncRewake). The PR diff against base 55f491f is 14 files, +162/-26.

## Residual risk
The fix depends on Claude Code keeping the hook's stderr inside the wake prompt. A future Claude Code that sets rewakeSummary or drops stderr from the body would turn the switch off again on every Signal continuation. The switch still has no expiry.
