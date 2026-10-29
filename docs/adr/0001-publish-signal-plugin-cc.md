# 0001. Publish signal-plugin-cc

Status: accepted, 2026-10-29

## Context

The repository `taoq-ai/signal-plugin-cc` is about to become public. Two choices were
hard to undo, so the owner decided both.

1. The history has 13 commits authored with `leone.lage@gmail.com`. Making the repository
   public publishes that address. The same address is already public in the commits of
   `taoq-ai/wuwei`.
2. The plugin was named `signal`, so it installed as `signal@signal-plugin-cc`. A bare
   `signal` can read as an official Signal integration, which the plugin directory's
   policy review may flag. Nobody has installed the plugin yet, so a rename costs no one
   a migration.

## Decision

1. Publish the history as is. No rewrite, no email scrub.
2. Rename the plugin to `signal-relay`. It installs as `signal-relay@signal-plugin-cc`.
   The repository name, the marketplace name `signal-plugin-cc`, the hooks and the config
   path `~/.config/signal-plugin-cc/` stay unchanged.

## Owner's answers

1. "one-way: making taoq-ai/signal-plugin-cc public publishes leone.lage@gmail.com on all
   13 commits ... I recommend publishing as is." Answer: Publish as is.
2. "one-way: the plugin installs as signal@signal-plugin-cc ... I recommend renaming the
   plugin to signal-relay." Answer: Rename to signal-relay.

## Consequences

- The author email is public and stays in the history. Rewriting it later would change
  every commit hash and break clones and open PRs.
- The install line is `/plugin install signal-relay@signal-plugin-cc`. Any note or
  script that used `signal@signal-plugin-cc` must change; none is known.
- Open PRs that edit `plugin.json` (plan-approval, version and description) merge beside
  this change, which touches only the `name` field.
