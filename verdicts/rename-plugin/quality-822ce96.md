Verdict: PASS
Gate: quality
Item: rename-plugin
PR: taoq-ai/signal-plugin-cc#7
Head: 822ce963d1cd841b6d552e311f35d15233e555e4
Confidence: high
Breaking: no

## Findings
none

## Probes
- Reviewed head 822ce96 (origin/chore/rename-plugin, equals the PR head per gh); diff against origin/main is 4 files, +42/-3.
- git archive copy: `claude plugin validate . --profile directory` printed "Validation passed". `python3 -m unittest discover -s tests`: 62 tests, OK.
- Hunks: plugin.json is the single `name` line (signal to signal-relay); marketplace.json is the single plugin `name` line, marketplace name stays `signal-plugin-cc`; README is the single install line, now `/plugin install signal-relay@signal-plugin-cc`. plugin.json version, description and the lines PR #5 edits are untouched, so the hunks do not overlap.
- Sweep of every remaining `signal-plugin-cc` and `signal@` occurrence at the head: the rest are the repository name or URLs, the marketplace name, the config path `~/.config/signal-plugin-cc`, stderr log prefixes, the WOKEN wake text, and the diagram SVGs and docs/diagram.py (product label, not an install name). All are deliberately kept, as the promise says (repository, hooks and config unchanged). No `signal@signal-plugin-cc` is left anywhere. hooks.json uses `${CLAUDE_PLUGIN_ROOT}` only, with no plugin-name coupling. No test, doc or diagram references the old plugin name.
- ADR check: the 13 commits and the single author leone.lage@gmail.com match `git rev-list --count origin/main` and `git log --format=%ae`. The decision text (publish as is; rename to signal-relay; repo name, marketplace name, hooks and config path unchanged) matches the item's promise and why, and both owner answers are quoted. The ADR claim that PR #5's plugin.json edits merge beside this change holds, since only `name` changes here.
- Test in diff: none. The PR body carries `No test: manifest, README and docs change; no code`, which is accepted because the change is manifests and docs and validate plus the suite pass. Guard mutants: no guard or validation changed, so none was run.
- Probes (parser or guard): none changed, so no parser probes apply.
- Simplicity: none. The diff is four small edits plus one ADR; the ADR is requested by the promise.

## Residual risk
The directory's safety scan and policy review, which `claude plugin validate` says it does not run, are untested, and the policy review is the reason for the rename. Any machine that already installed `signal@signal-plugin-cc` would need a reinstall; the owner says there is none.
