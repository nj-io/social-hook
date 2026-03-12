# Changelog

## [0.5.0](https://github.com/nj-io/social-hook/compare/social-hook-v0.4.0...social-hook-v0.5.0) (2026-03-10)


### Features

* ✨ cross-post references with abstract adapter interface ([#19](https://github.com/nj-io/social-hook/issues/19)) ([7793518](https://github.com/nj-io/social-hook/commit/779351846b3f8cc8352ed0d1b4c340099d15e23d))
* ✨ snapshot CLI, E2E test suite split, and E2E snapshot integration ([#14](https://github.com/nj-io/social-hook/issues/14)) ([5896820](https://github.com/nj-io/social-hook/commit/589682082c5f4216214369570e5d29b34683385c))
* snapshots, decision rewind, cross-post references, and E2E overhaul ([40403a5](https://github.com/nj-io/social-hook/commit/40403a5c4bbf840766d954fea799a5d6d5c7c9e1))


### Bug Fixes

* 🐛 media generation fixes, CLI improvements, and E2E coverage ([87a6eef](https://github.com/nj-io/social-hook/commit/87a6eef4de5e01d6f170f1303f26917e740cadd8))
* 🐛 snapshot restore WAL corruption and flaky bot status test ([cc1ada1](https://github.com/nj-io/social-hook/commit/cc1ada10de237e7d665bfcf849bf67c1863f6cca))
* 🐛 snapshot restore/reset refuse while bot daemon is running ([095b374](https://github.com/nj-io/social-hook/commit/095b37421a8cbfe3fea32f185b19222ef943d918))
* 🐛 stale background task recovery + manual draft content filter bypass ([#16](https://github.com/nj-io/social-hook/issues/16)) ([8690d5d](https://github.com/nj-io/social-hook/commit/8690d5d9a418052483e1db14f144cebf7488c92b))
* resolve lint and typecheck CI failures ([1937cf9](https://github.com/nj-io/social-hook/commit/1937cf9398b455c4a2a1aa013f2bb485e2c351d1))

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
