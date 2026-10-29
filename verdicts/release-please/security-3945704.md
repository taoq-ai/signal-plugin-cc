Verdict: PASS
Gate: security
Item: release-please
PR: taoq-ai/signal-plugin-cc#9
Head: 39457042e2a60dd778ebdc97c7c7116a455fe9b9
Confidence: high

## Findings
- [low] blocks: no. Repo setting can_approve_pull_request_reviews is true and main has no branch protection or ruleset. The same toggle ("Allow GitHub Actions to create and approve pull requests") is what lets release-please open its PR with GITHUB_TOKEN, so turning it off breaks this item. Before the repo goes public, the owner should either add a ruleset on main that requires a code-owner review (an approval from github-actions[bot] does not count as a code-owner review), or move release-please to a GitHub App token and then turn the setting off (CWE-284, OWASP A01).
- [low] blocks: no. GitHub does not run tests.yml on the release PR because GITHUB_TOKEN opens it. The PR only changes CHANGELOG.md, .release-please-manifest.json and the plugin.json version, and tests.yml runs on main after the merge. Accepted as stated in the PR body.
- [low] .github/workflows/release-please.yml:16 blocks: no. The pinned v4.4.1 action uses `runs: node20`. Upstream also has a v5 tag. I did not compare them, so this is a maintenance note and has no security effect.

## Probes
- Pin provenance: `git ls-remote https://github.com/googleapis/release-please-action 'refs/tags/v4*'` shows refs/tags/v4.4.1 (a lightweight tag), v4^{} and v4.4^{} all at 5c625bfb5d1ff62eadeeb3772007f7f66fdcf071. The owner is googleapis, the upstream repo.
- Action source at that sha: I fetched it into scratch (`git fetch --depth 1 ... 5c625bf`). action.yml defaults `token` to github.token and runs dist/index.js on node20.
- No approval or merge: in dist/index.js the only `pulls.createReview` call (line 19020, code-suggester makeInlineSuggestions) uses `event: 'COMMENT'`. There is no call to `pulls.merge`, `mergePullRequest` (only a local variable name in commit parsing) or `enablePullRequestAutoMerge`. The config does not ask for auto-merge, and allow_auto_merge is false on the repo.
- Shell injection: the workflow has only the single `uses:` step. There is no `run:`, no `${{ }}` expression on untrusted data, no checkout, and no consumer of the action outputs. Commit messages and PR titles go only to the action's JS (Octokit API calls) and into the markdown of CHANGELOG.md and the release notes. Trigger is `push: branches: [main]` only, with no pull_request_target.
- Permissions: workflow-level `permissions: {}`; the one job has contents: write and pull-requests: write. No secrets beyond GITHUB_TOKEN. Repo default_workflow_permissions is read. tests.yml is unchanged (contents: read, pull_request).
- Release PR file set: Simple strategy (dist/index.js:54526) updates CHANGELOG.md (createIfMissing true) and version.txt (createIfMissing false). version.txt is absent at the head (`ls` in the archive copy), so the PR touches CHANGELOG.md, the manifest and the extra-files path .claude-plugin/plugin.json `$.version`, and nothing else.
- Repo state (read only, 4 gh calls): private, allow_auto_merge false, main "Branch not protected" (404), rulesets [].
- Tests at head in a `git archive` copy: `python3 -I -m unittest discover -s tests` ran 77 tests, OK. The suite uses temporary SIGNAL_CC_HOME directories and ephemeral stub ports; the 8299 in it is only an assertion on the default value.
- Mutants (fresh copies, `-p test_release.py`): extra-files path changed to plugin.json makes test_release_bumps_plugin_json_version FAIL; initial-version 0.1.0 makes test_manifest_matches_plugin_json FAIL; the head runs OK.
- Scanner: the repo's CI runs no secret, dependency or workflow scanner, and zizmor, actionlint and gitleaks are not installed locally, so that is unmeasured. No secret appears in the 70-line diff on manual read.
- Confidence high: I read the pinned action source directly, the workflow has no shell surface, and the token scope is minimal. A future change that adds a run step consuming the action outputs, or a token swap, would change this.

## Residual risk
Commit text lands unescaped in public release notes, which is markdown only and rendered by GitHub. While the setting that lets Actions approve PRs stays on, with no protection on main, the owner's review is not enforced by the platform.
