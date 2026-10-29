# Changelog

## [0.3.1](https://github.com/taoq-ai/signal-plugin-cc/compare/v0.3.0...v0.3.1) (2026-10-29)


### Bug Fixes

* refuse a foreign config home, unsafe session ids and symlinked cleanup ([#11](https://github.com/taoq-ai/signal-plugin-cc/issues/11)) ([3771618](https://github.com/taoq-ai/signal-plugin-cc/commit/377161846bdc514841d26346ce5d207d3a26982c))

## 0.3.0 (2026-10-29)


### ⚠ BREAKING CHANGES

* relay plan approval (ExitPlanMode) to Signal ([#5](https://github.com/taoq-ai/signal-plugin-cc/issues/5))

### Features

* record every relay outcome in relay.log ([#3](https://github.com/taoq-ai/signal-plugin-cc/issues/3)) ([e303348](https://github.com/taoq-ai/signal-plugin-cc/commit/e303348b32624a95b49d1ebfb2ab1d655ee2d100))
* relay plan approval (ExitPlanMode) to Signal ([#5](https://github.com/taoq-ai/signal-plugin-cc/issues/5)) ([9947c90](https://github.com/taoq-ai/signal-plugin-cc/commit/9947c90ed2034fdaee3480c0ba3b2032fe5f6e3a))
* release with release-please, first release v0.3.0 ([#9](https://github.com/taoq-ai/signal-plugin-cc/issues/9)) ([9d6cefe](https://github.com/taoq-ai/signal-plugin-cc/commit/9d6cefebfaf1b9396973487492b39a575be324a5))
* tell Signal when the Mac takes over a finished session's message ([#6](https://github.com/taoq-ai/signal-plugin-cc/issues/6)) ([ba5a872](https://github.com/taoq-ai/signal-plugin-cc/commit/ba5a872f6fca129f32bbebd91ff8ab88a4af3c4d))


### Bug Fixes

* keep the config home 0700 and its files 0600, never written through a symlink ([#8](https://github.com/taoq-ai/signal-plugin-cc/issues/8)) ([0e70533](https://github.com/taoq-ai/signal-plugin-cc/commit/0e7053371f146d237502a8eaa5da4d87fe036387))
* no Stop listener in claude -p runs, and silent hooks without fcntl ([#4](https://github.com/taoq-ai/signal-plugin-cc/issues/4)) ([c7d7222](https://github.com/taoq-ai/signal-plugin-cc/commit/c7d7222cac3f4fcce0681dd6a17bc3f7092af226))
