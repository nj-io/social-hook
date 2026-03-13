# Changelog

## [0.8.0](https://github.com/nj-io/social-hook/compare/social-hook-v0.7.0...social-hook-v0.8.0) (2026-03-13)


### Features

* setup wizard overhaul — strategy-first onboarding + identity wiring ([bf9faec](https://github.com/nj-io/social-hook/commit/bf9faec5cf7a937c103205c1473cc27b32abea9e))


### Bug Fixes

* add None check for get_project return in quickstart ([8df6093](https://github.com/nj-io/social-hook/commit/8df60936b2787eda7b55c3f5a88fb3eb895db5b3))

## [0.7.0](https://github.com/nj-io/social-hook/compare/social-hook-v0.6.0...social-hook-v0.7.0) (2026-03-13)


### Features

* ⚡ pipeline rate limits and merge queue execution ([#33](https://github.com/nj-io/social-hook/issues/33)) ([4380d10](https://github.com/nj-io/social-hook/commit/4380d101ec1b92c79c295b4c883212cf879f630d))
* add CLI spinner with elapsed counter for slow operations ([405f6d2](https://github.com/nj-io/social-hook/commit/405f6d22e7648babc10f4afc806b0df41ea71d0e))
* add favicon and social preview assets ([5c52940](https://github.com/nj-io/social-hook/commit/5c529409a904eb405aeea183b0c7af8e3fe1d280))
* add landing page site ([d24266e](https://github.com/nj-io/social-hook/commit/d24266e3b7664b87a39221b6b00497fe9d908171))
* landing page for GitHub Pages ([39494a2](https://github.com/nj-io/social-hook/commit/39494a2d6190ab29c968c27eeac60831deab1841))
* landing page for GitHub Pages ([#34](https://github.com/nj-io/social-hook/issues/34)) ([b4a84aa](https://github.com/nj-io/social-hook/commit/b4a84aab2f724f575133182f7f7eeb72150a1c55))
* landing page mobile cascade, favicon, and social preview ([949c8c8](https://github.com/nj-io/social-hook/commit/949c8c80d3b59d64174f2cf52512cf56df84f5cc))
* mobile-responsive cascade animation with vertical pyramid layout ([2c6e7c5](https://github.com/nj-io/social-hook/commit/2c6e7c506466d186a3d7e095f94a56defab80f4c))
* preview platform overhaul, promote flow, and post now ([cbb22de](https://github.com/nj-io/social-hook/commit/cbb22de3bf31d0e15df6eb4c1f58f9fe92285dce))
* preview platform overhaul, promote flow, post now, and CLI spinners ([b32db14](https://github.com/nj-io/social-hook/commit/b32db14c358900ebb1072a3914fc65ed8a6cef80))
* reversible draft actions, button restoration, and lifecycle toasts ([c6eb3cd](https://github.com/nj-io/social-hook/commit/c6eb3cd8d0077924cf518c8d899b2bb1a6942cc0))
* reversible draft actions, button restoration, and lifecycle toasts ([d4471a2](https://github.com/nj-io/social-hook/commit/d4471a2a6587e82019581c5ec41366e18848b0be))


### Bug Fixes

* landing page copy updates and animation fixes ([03e0562](https://github.com/nj-io/social-hook/commit/03e05625c6485fa186c2d15b3fd106da7e24c342))
* type annotate button handlers dict to fix mypy dict-item errors ([269693b](https://github.com/nj-io/social-hook/commit/269693b4a9ad9f190ff58233d4a093291df24089))

## [0.6.0](https://github.com/nj-io/social-hook/compare/social-hook-v0.5.0...social-hook-v0.6.0) (2026-03-12)


### Features

* ✨ elapsed timer system + slow task banner ([#28](https://github.com/nj-io/social-hook/issues/28)) ([4b7d477](https://github.com/nj-io/social-hook/commit/4b7d47797f73e1134af0091a4bf56da911510a9c))
* discovery improvements — per-file summaries, prompt docs, auto-refresh ([#25](https://github.com/nj-io/social-hook/issues/25)) ([e2fd6d7](https://github.com/nj-io/social-hook/commit/e2fd6d74925b52dc1f7732408fc26b07a205fe7d))
* edit media overhaul + bot daemon reliability ([#29](https://github.com/nj-io/social-hook/issues/29)) ([cafad1e](https://github.com/nj-io/social-hook/commit/cafad1e40d80b71d67a11aa0de8bed37b3038807))
* rate limits, config tiers, snapshot restore fix, and pipeline feedback ([4d4bab2](https://github.com/nj-io/social-hook/commit/4d4bab2a4de3326e2a2155f300d43ac080a160c8))


### Bug Fixes

* resolve lint and typecheck CI failures ([#27](https://github.com/nj-io/social-hook/issues/27)) ([4600f37](https://github.com/nj-io/social-hook/commit/4600f3717702f49b2b0c8748388f3c87068c56c4))

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
