# Changelog

## [0.5.0](https://github.com/nj-io/social-hook/compare/social-hook-v0.4.0...social-hook-v0.5.0) (2026-03-10)


### Features

* snapshots, decision rewind, cross-post references, and E2E overhaul ([#22](https://github.com/nj-io/social-hook/issues/22)) ([5a5d710](https://github.com/nj-io/social-hook/commit/5a5d7109565a7a7e2cb02a78a0f23f8caab6b379))

## [0.4.0](https://github.com/nj-io/social-hook/compare/social-hook-v0.3.0...social-hook-v0.4.0) (2026-03-09)


### Features

* scheduler rework, commit import, and project management ([#12](https://github.com/nj-io/social-hook/issues/12)) ([456acd2](https://github.com/nj-io/social-hook/commit/456acd2b6d7e953df7f62f9c0d911bfda027d0c3))

## [0.3.0](https://github.com/nj-io/social-hook/compare/social-hook-v0.2.1...social-hook-v0.3.0) (2026-03-07)


### ⚠ BREAKING CHANGES

* _generate_media() signature changed from (config, evaluation) to (config, media_type_str, media_spec_dict). DB migration 014 adds media_spec_used column.

### Features

* ✨ Add background tasks infrastructure ([e51227b](https://github.com/nj-io/social-hook/commit/e51227b7a4774d2cbbebd5dbf56add4227f81349))
* ✨ Send draft review notifications from web API endpoints ([7563066](https://github.com/nj-io/social-hook/commit/75630664328eee455d4fb03c33f6508e008de65c))
* Decision management, media error surfacing, draft filtering ([0ecfd77](https://github.com/nj-io/social-hook/commit/0ecfd7799c8c0aba4437d6a472572699d6c9bca1))


### Bug Fixes

* 🐛 Fix CI test failures and missing type stubs ([ae5a728](https://github.com/nj-io/social-hook/commit/ae5a7289ca1cf0942b71f0010afa2a4dafb69f54))
* 🐛 Fix media spec pipeline — drafter produces spec, not empty dict ([47a5191](https://github.com/nj-io/social-hook/commit/47a5191bd3e9a3356c922cb78f1f0d5a7d3a2b8f))
* 🐛 Strip ANSI codes from CLI help output in tests ([ed9f591](https://github.com/nj-io/social-hook/commit/ed9f59127f2633697a317ceb2fde139a2024ae1d))
* 🐛 Unify notification routing, fix reply capture, and clear stale buttons ([7865c47](https://github.com/nj-io/social-hook/commit/7865c47398e84d0a02a915cf55eb4f9532fc78cb))
* 🐛 Wire up Change Angle to Expert agent, save memory on Reject with Note ([0e3f551](https://github.com/nj-io/social-hook/commit/0e3f551008ed1e130b7c080191b888f541bbb1b2))
