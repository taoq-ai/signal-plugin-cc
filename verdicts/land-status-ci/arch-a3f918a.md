Verdict: FIX
Gate: arch
Item: land-status-ci
PR: taoq-ai/signal-plugin-cc
Head: a3f918a1c248d5c527029bb9adfbb3f8faa94cb2
Confidence: high
Breaking: no   (minor: adds the `desk` handler and the `status` command; hooks.json, the config keys and every prompt text are unchanged; the removed modules signal_cc.hooks/ask/daemon/presence were internal and not declared API at 8f0252e)

## Findings
- [medium] tests/test_architecture.py:26 blocks: yes. Failure: the fitness function counts only relative imports (`node.level`), so `from signal_cc.adapters import files` or `import signal_cc.entry.wiring` added to signal_cc/domain/routing.py passes the test, while README.md:107 states that it "fails on any import that points outward"; a layering break written as an absolute import lands with CI green (design rule README "Architecture", charter arch rule 5)
- [medium] signal_cc/entry/hooks.py:84 blocks: yes. Failure: run_desk picks the port adapters itself (`desk.serve(SignalCli(cfg), FileRegistry(cfg.home))`, and SignalCli again at hooks.py:67 and :79), contradicting README.md:115 and entry/wiring.py:1, which name wiring.py as "the one place that picks adapters"; whoever swaps or fakes an adapter in wiring.py leaves the desk on the old one (design rule README "Architecture"). Either build the desk in wiring.py or narrow the README and docstring wording
- [low] signal_cc/app/conversation.py:36 blocks: no. Reverting the claim ttl to `self.wait` (the 8f0252e behaviour, the brief's "listener claim lasts as long as it listens") passes all 33 tests; no test pins it
- [low] signal_cc/app/conversation.py:70 blocks: no. Replacing `return value` on stream end with `continue` passes all 33 tests (the stream-end test just waits out its 10 s deadline 10 s later); the test does not tell the two apart
- [low] signal_cc/app/conversation.py:70 blocks: no. Behaviour change outside the brief's two named ones: when the daemon's stream ends, a prompt returns at once with no "Timed out" message, and a multi-select answer still settling returns without its receipt. Commit bfd4908 records it; the PR body should list it under Assumptions
- [low] .github/workflows/tests.yml:13 blocks: no. The matrix (3.10, 3.14, as the plan fixes) skips 3.9, which is what hooks.json's `python3` runs on stock macOS (/usr/bin/python3 3.9.6); 33/33 pass on 3.9.6 locally today, but nothing keeps that true
- [low] README.md:83 blocks: no. "Send `status` at any time" overstates it: the desk exits when the event stream ends, or after 60 s with no daemon, and then nothing answers `status` until the next SessionStart; after a plugin update an old desk keeps running the old code until the stream ends
- [low] .github/workflows/tests.yml:15 blocks: no. Actions are pinned by tag, not by sha, and there is no `permissions:` block; this belongs to the security gate, noted here only

## Probes
- head confirmed: git rev-parse a3f918a = feat/status-ci-architecture = a3f918a1c248d5c527029bb9adfbb3f8faa94cb2; base origin/main 8f0252e; trees from git archive into scratch.
- tests at head: `python3 -m unittest discover -s tests` Ran 33, OK on /usr/bin/python3 3.9.6 and on /opt/homebrew/bin/python3.14 3.14.5. The Linux CI runners (3.10 and 3.14) were not measured: no local python image and no network pull.
- fitness-function mutants (each in a fresh copy, `discover -s tests -p test_architecture.py`): relative imports app->adapters, domain->app, domain->config, adapters->entry, ports->app all FAIL as intended; the absolute imports `from signal_cc.adapters import files` and `import signal_cc.entry.wiring` in domain/routing.py both stay OK (finding 1).
- routing differential, base ask() inline logic vs head domain.routing.route, 200000 random cases (tags, quotes, votes, live sets, latest): 0 unexpected differences. 5280 differ, all of them a bare `status` (no quote, no votes) that the head SKIPs, which is the intended desk change.
- forms differential, base hooks.permission/question/listen (ask stubbed) vs head PermissionForm/QuestionForm/ContinueForm: 300 permission, 300 multi-question and 20 continue cases, covering text, polls, parse over 12 replies or 4 replies with targets and votes, and receipts. The two outputs are byte-identical (472087 bytes each).
- event-parsing differential, base Daemon._read_lines vs head SignalCli.parse_event, 20000 random envelopes (dataMessage/syncMessage, owner/other, vote/reaction/quote, malformed): identical; 1076 yield a Reply.
- contracts: hooks/hooks.json is unchanged (the diff is empty); Config fields are unchanged (only the internal `pending` property is gone, and grep finds no remaining user); relay.py handler names are a superset (desk added); README prompt formats and tag routing are unchanged apart from the added `status` line.
- mutants on the changes: removing the command SKIP in route fails 2 tests; the claim ttl reverted to self.wait survives (re-run in a fresh copy: 33 OK); the stream-end return replaced by continue survives (re-run in a fresh copy: 33 OK, 23.2 s against 13.2 s).
- desk and prompt race: when the desk marks `last` from a status computed before a new claim, the result is still safe, because route takes a plain reply only when its prompt is the sole live one.
- Confidence high: the differentials cover the restructure's behaviour-preservation claim, and both blocking findings are reproduced with a named input or cited lines.

## Residual risk
The desk lifecycle (one process per Mac, ending with the daemon stream) is new operational state with only a stub-daemon test. Whether the Linux CI runners pass is unmeasured until the PR runs.
