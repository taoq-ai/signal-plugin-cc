Verdict: PASS
Gate: quality
Item: away-switch
PR: taoq-ai/signal-plugin-cc#2
Head: 94be9750b29841d44d3c36fa04943338f0f3565a
Confidence: medium
Breaking: no

## Findings
- [medium] signal_cc/entry/hooks.py:40 blocks: no. Note: quiet() turns the switch off on every UserPromptSubmit, and no test pins what a Signal-woken turn does; if Claude Code fires UserPromptSubmit when the Stop listener wakes the session (exit 2 with the reply), an owner who sent `away` and then answers a continuation from Signal turns the switch off with no Mac input, and the next prompt follows idle time again (at the Mac in a meeting it stays on the Mac). I could not run a real Claude Code turn, so the firing is taken from the brief's hooks-reference claim, unverified here; the code matches the promise's literal wording (UserPromptSubmit). Decide the intended behaviour and pin it with a test (for example quiet() on a UserPromptSubmit with the wake message, assert the switch state).
- [low] signal_cc/entry/hooks.py:40 blocks: no. Note: the switch turns off only when the hook input carries hook_event_name == "UserPromptSubmit"; if the field were ever absent the switch would stay on silently. The test passes the field by hand, so it cannot show that Claude Code sends it.
- [low] tests/test_adapters.py:182 blocks: no. Note: the away end-to-end test waits with time.sleep(0.5/0.3) for the desk to subscribe and answer. It is the same pattern as the existing status desk test and passed 4 of 4 repeat runs, so it is a flake risk only on a slow CI runner.
- [low] tests/test_app.py:136 blocks: no. Note: acceptance 2 (switch on, Mac input while a prompt waits, prompt stays on Signal) is pinned at the presence level (returned() is False with the switch on, mutant M4) but no Conversation-level test runs _collect with the switch on; acceptance 4 (unknown idle sends nothing) likewise stops at presence.away().

## Probes
- Tests, `python3 -m unittest discover -s tests` on `git archive` copies: head 41 tests OK on 3.14.5, on stock /usr/bin/python3 3.9.6 and on 3.13 (3.10 not installed here: unmeasured; CI covers it); origin/main 55f491f 36 tests OK on 3.14.5 and 3.9.6. Head adds 5 tests; none skipped. The head's new tests use the new Presence/AwaySwitch/status signatures that do not exist on main, so they cannot pass there.
- Mutants on a full-tree copy of the head, baseline passing, 18 runs (copies under the scratchpad quality-away-switch/mut): null mutant M0 (docstring) survived as required. Killed 17 of 17 real mutants, each by a named test: COMMANDS without away (test_away_and_back_flip_the_switch_and_status_shows_it, test_away_from_signal_sends_the_next_prompt_there_though_the_mac_is_in_use) and without back (test_a_reply_never_crosses_to_another_prompt, desk test); away() ignoring the switch and returned() ignoring it (test_the_switch_overrides_idle_time_and_unknown_idle_means_at_the_mac, end-to-end away test); unknown idle counted as away (same presence test, idle=None, switch off); back not clearing (desk test); swapped confirmation texts (desk test); desk dropping mark_latest("") replaced by pass (desk test, the first attempt left an empty branch and was a syntax error, rerun as M8b); quiet() without the switch-off (test_a_prompt_typed_at_the_mac_turns_the_switch_off_and_session_end_does_not) and quiet() clearing on any event (same test); status text without the switch in the empty and non-empty branches (test_texts, desk test); status passed False (desk test); AwaySwitch.set without mkdir, on() always False, off as no-op (PresenceTest.test_the_switch_is_shared_through_the_config_home, hook test); wiring pointing the switch at another home (hooks test).
- The quoted `away` reply (acceptance 5) is pinned in the domain routing table (Take, not SKIP) and in the desk test (Reply("away", 1001) leaves the switch on its state). Listener wake path: listen() calls quiet() with a Stop event, so it does not clear the switch (SessionEnd case pinned; Stop not directly pinned).
- Signal-woken turn: no test in the diff calls quiet() with a woken-turn UserPromptSubmit or discusses it; the intended behaviour is not pinned (see the medium note).
- No closed findings (first round).

Simplicity: none to delete. MacPresence.set_switch and switch_on are one-line pass-throughs, but they put the switch behind the existing Presence port so desk.py stays free of adapters (test_architecture enforces the layering); a separate Switch port would be a second one-implementation abstraction.

## Residual risk
The Signal-woken UserPromptSubmit behaviour is unverified against a real Claude Code run and unpinned; it decides whether the switch survives the main "in a meeting at the Mac" flow. Python 3.10 was not run locally.
