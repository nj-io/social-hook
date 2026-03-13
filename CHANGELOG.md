# Changelog

## [0.10.0](https://github.com/nj-io/social-hook/compare/v0.9.0...v0.10.0) (2026-03-13)


### ⚠ BREAKING CHANGES

* _generate_media() signature changed from (config, evaluation) to (config, media_type_str, media_spec_dict). DB migration 014 adds media_spec_used column.

### Features

* ⚡ pipeline rate limits and merge queue execution ([#33](https://github.com/nj-io/social-hook/issues/33)) ([4380d10](https://github.com/nj-io/social-hook/commit/4380d101ec1b92c79c295b4c883212cf879f630d))
* ✨ Add background tasks infrastructure ([e51227b](https://github.com/nj-io/social-hook/commit/e51227b7a4774d2cbbebd5dbf56add4227f81349))
* ✨ add deferred draft status with schema migration ([4326fdf](https://github.com/nj-io/social-hook/commit/4326fdf7bcf952c61e85a8cd6a9a694f84dfea38))
* ✨ add deferred status to CLI, web, and bot interfaces ([378e868](https://github.com/nj-io/social-hook/commit/378e868d214be7a72edba68f019ca26fc9260519))
* ✨ auto-promote deferred drafts in scheduler tick ([592cdb9](https://github.com/nj-io/social-hook/commit/592cdb91c300fc50502f86afe3bdb14334d25262))
* ✨ create deferred drafts instead of silent skip, add scheduling state gathering ([510e1aa](https://github.com/nj-io/social-hook/commit/510e1aa01efb40ab614dcb809fd9648eed6f15a7))
* ✨ cross-post references with abstract adapter interface ([#19](https://github.com/nj-io/social-hook/issues/19)) ([7793518](https://github.com/nj-io/social-hook/commit/779351846b3f8cc8352ed0d1b4c340099d15e23d))
* ✨ elapsed timer system + slow task banner ([#28](https://github.com/nj-io/social-hook/issues/28)) ([4b7d477](https://github.com/nj-io/social-hook/commit/4b7d47797f73e1134af0091a4bf56da911510a9c))
* ✨ inject scheduling state into evaluator prompt ([fa78054](https://github.com/nj-io/social-hook/commit/fa78054690a8a161fbfa407c6590e41f13cde4ce))
* ✨ Send draft review notifications from web API endpoints ([7563066](https://github.com/nj-io/social-hook/commit/75630664328eee455d4fb03c33f6508e008de65c))
* ✨ Show reasoning as permanent column in decisions table ([2aac50c](https://github.com/nj-io/social-hook/commit/2aac50ce7268d44248e0bc13b73cce9409e45c96))
* ✨ snapshot CLI, E2E test suite split, and E2E snapshot integration ([#14](https://github.com/nj-io/social-hook/issues/14)) ([5896820](https://github.com/nj-io/social-hook/commit/589682082c5f4216214369570e5d29b34683385c))
* add CLI spinner with elapsed counter for slow operations ([405f6d2](https://github.com/nj-io/social-hook/commit/405f6d22e7648babc10f4afc806b0df41ea71d0e))
* add community files and polish packaging metadata ([e835cf9](https://github.com/nj-io/social-hook/commit/e835cf9ceb24fb6ef00322333f6f4a0a885d69a3))
* add favicon and social preview assets ([5c52940](https://github.com/nj-io/social-hook/commit/5c529409a904eb405aeea183b0c7af8e3fe1d280))
* add historical commit importing and branch filtering ([b56c342](https://github.com/nj-io/social-hook/commit/b56c34228743084c407cec40608dc45e4553f7df))
* add landing page site ([d24266e](https://github.com/nj-io/social-hook/commit/d24266e3b7664b87a39221b6b00497fe9d908171))
* add logo, favicon, and social preview banner ([9240879](https://github.com/nj-io/social-hook/commit/9240879d57452fa8302624a1a18d4cf3c401c6a2))
* add MkDocs documentation site and CLI docs generator ([88cddb6](https://github.com/nj-io/social-hook/commit/88cddb6656147824b754630e6be700f200d2442c))
* CLI wizard restructure + quickstart + batch evaluate ([688d9d0](https://github.com/nj-io/social-hook/commit/688d9d074df176489e3618b4728ce7f30971e688))
* Decision management, media error surfacing, draft filtering ([0ecfd77](https://github.com/nj-io/social-hook/commit/0ecfd7799c8c0aba4437d6a472572699d6c9bca1))
* discovery improvements — per-file summaries, prompt docs, auto-refresh ([#25](https://github.com/nj-io/social-hook/issues/25)) ([e2fd6d7](https://github.com/nj-io/social-hook/commit/e2fd6d74925b52dc1f7732408fc26b07a205fe7d))
* edit media overhaul + bot daemon reliability ([#29](https://github.com/nj-io/social-hook/issues/29)) ([cafad1e](https://github.com/nj-io/social-hook/commit/cafad1e40d80b71d67a11aa0de8bed37b3038807))
* identity wiring into drafter/expert + bundled prompt defaults ([87bdbba](https://github.com/nj-io/social-hook/commit/87bdbba2cdb3a16c5b9eb919f4978514b0c86b71))
* landing page for GitHub Pages ([39494a2](https://github.com/nj-io/social-hook/commit/39494a2d6190ab29c968c27eeac60831deab1841))
* landing page for GitHub Pages ([#34](https://github.com/nj-io/social-hook/issues/34)) ([b4a84aa](https://github.com/nj-io/social-hook/commit/b4a84aab2f724f575133182f7f7eeb72150a1c55))
* landing page mobile cascade, favicon, and social preview ([949c8c8](https://github.com/nj-io/social-hook/commit/949c8c80d3b59d64174f2cf52512cf56df84f5cc))
* mobile-responsive cascade animation with vertical pyramid layout ([2c6e7c5](https://github.com/nj-io/social-hook/commit/2c6e7c506466d186a3d7e095f94a56defab80f4c))
* named identity definitions + per-platform introduction tracking ([6b3275f](https://github.com/nj-io/social-hook/commit/6b3275face88ffc10c63477a584a5bd3fc41484e))
* OSS publish prep — docs site, CLI fixes, community files ([62a4343](https://github.com/nj-io/social-hook/commit/62a43436699504b7224e4e68d68624c5814fb608))
* overhaul CLI help system and --json flag placement ([dbc5569](https://github.com/nj-io/social-hook/commit/dbc5569573c9b9493395261b19ba30dd52abb563))
* preview platform overhaul, promote flow, and post now ([cbb22de](https://github.com/nj-io/social-hook/commit/cbb22de3bf31d0e15df6eb4c1f58f9fe92285dce))
* preview platform overhaul, promote flow, post now, and CLI spinners ([b32db14](https://github.com/nj-io/social-hook/commit/b32db14c358900ebb1072a3914fc65ed8a6cef80))
* rate limits, config tiers, snapshot restore fix, and pipeline feedback ([4d4bab2](https://github.com/nj-io/social-hook/commit/4d4bab2a4de3326e2a2155f300d43ac080a160c8))
* reversible draft actions, button restoration, and lifecycle toasts ([c6eb3cd](https://github.com/nj-io/social-hook/commit/c6eb3cd8d0077924cf518c8d899b2bb1a6942cc0))
* reversible draft actions, button restoration, and lifecycle toasts ([d4471a2](https://github.com/nj-io/social-hook/commit/d4471a2a6587e82019581c5ec41366e18848b0be))
* scheduler rework, commit import, and project management ([#12](https://github.com/nj-io/social-hook/issues/12)) ([456acd2](https://github.com/nj-io/social-hook/commit/456acd2b6d7e953df7f62f9c0d911bfda027d0c3))
* scheduling-aware evaluator + deferred drafts ([#8](https://github.com/nj-io/social-hook/issues/8)) ([3b340a2](https://github.com/nj-io/social-hook/commit/3b340a21e215ba7ebc7c046001f0083839d755d9))
* setup wizard overhaul — strategy-first onboarding + identity wiring ([bf9faec](https://github.com/nj-io/social-hook/commit/bf9faec5cf7a937c103205c1473cc27b32abea9e))
* snapshots, decision rewind, cross-post references, and E2E overhaul ([40403a5](https://github.com/nj-io/social-hook/commit/40403a5c4bbf840766d954fea799a5d6d5c7c9e1))
* Universal git post-commit hook + web project registration ([#9](https://github.com/nj-io/social-hook/issues/9)) ([3a740a0](https://github.com/nj-io/social-hook/commit/3a740a04163b178bab349653bca2f0c2a5d4841f))
* update docs for new CLI commands, add coverage badge ([514dae3](https://github.com/nj-io/social-hook/commit/514dae3be612269ab6443977938e67dc021f112d))
* **web:** add batch evaluate button to project floating action bar ([34e0f25](https://github.com/nj-io/social-hook/commit/34e0f25cdbd764c815bfa878ffc6f6676b621642))
* **web:** add quickstart modal, empty states, and metadata pills ([d1302ea](https://github.com/nj-io/social-hook/commit/d1302ea054ebebcb8fbb7277d265e8c6f5bddfb1))
* **web:** add setup wizard modal with 9-step guided flow ([ab13e45](https://github.com/nj-io/social-hook/commit/ab13e453db1a9533a80601c7dd22899874d957ed))
* wire summary-draft endpoint + discovery for wizard/quickstart flows ([03517b2](https://github.com/nj-io/social-hook/commit/03517b2f0b53130ed5553a55bc4b83ecdb294fd4))


### Bug Fixes

* 🐛 add deferred status tab to web UI, fix JSX syntax error ([98ce927](https://github.com/nj-io/social-hook/commit/98ce927529c250a1504ddb347f753de9d143ddf4))
* 🐛 Detect git commit in chained commands (&&) ([7bf3c8e](https://github.com/nj-io/social-hook/commit/7bf3c8e11d1588461c2ffe1068c72c0d69f4168d))
* 🐛 Fix CI test failures and missing type stubs ([ae5a728](https://github.com/nj-io/social-hook/commit/ae5a7289ca1cf0942b71f0010afa2a4dafb69f54))
* 🐛 Fix JSX syntax error and add TypeScript pre-commit check ([96773f2](https://github.com/nj-io/social-hook/commit/96773f262df9f4e0deecd9e3938b84df25f8f212))
* 🐛 Fix media spec pipeline — drafter produces spec, not empty dict ([47a5191](https://github.com/nj-io/social-hook/commit/47a5191bd3e9a3356c922cb78f1f0d5a7d3a2b8f))
* 🐛 Fix mypy type errors across codebase ([7a06701](https://github.com/nj-io/social-hook/commit/7a06701c7e37b58a9e1789733035efa655e3dc33))
* 🐛 Fix mypy type errors in prompts.py and operations.py ([c90eb64](https://github.com/nj-io/social-hook/commit/c90eb6497f324a65fbbac3a55e0c8dd756f0a28a))
* 🐛 isolate worktree databases to prevent migration collisions ([14b3363](https://github.com/nj-io/social-hook/commit/14b3363f751c0a04e0448c8ed1eff86684d99011))
* 🐛 media generation fixes, CLI improvements, and E2E coverage ([87a6eef](https://github.com/nj-io/social-hook/commit/87a6eef4de5e01d6f170f1303f26917e740cadd8))
* 🐛 snapshot restore WAL corruption and flaky bot status test ([cc1ada1](https://github.com/nj-io/social-hook/commit/cc1ada10de237e7d665bfcf849bf67c1863f6cca))
* 🐛 snapshot restore/reset refuse while bot daemon is running ([095b374](https://github.com/nj-io/social-hook/commit/095b37421a8cbfe3fea32f185b19222ef943d918))
* 🐛 stale background task recovery + manual draft content filter bypass ([#16](https://github.com/nj-io/social-hook/issues/16)) ([8690d5d](https://github.com/nj-io/social-hook/commit/8690d5d9a418052483e1db14f144cebf7488c92b))
* 🐛 Strip ANSI codes from CLI help output in tests ([ed9f591](https://github.com/nj-io/social-hook/commit/ed9f59127f2633697a317ceb2fde139a2024ae1d))
* 🐛 Unify notification routing, fix reply capture, and clear stale buttons ([7865c47](https://github.com/nj-io/social-hook/commit/7865c47398e84d0a02a915cf55eb4f9532fc78cb))
* 🐛 Wire up Change Angle to Expert agent, save memory on Reject with Note ([0e3f551](https://github.com/nj-io/social-hook/commit/0e3f551008ed1e130b7c080191b888f541bbb1b2))
* add forgiving --json flag to rate-limits command ([25266cd](https://github.com/nj-io/social-hook/commit/25266cdce6ae111e2058b04ad66d130ef89e2674))
* add forgiving --json flag to rate-limits command ([836b3e4](https://github.com/nj-io/social-hook/commit/836b3e486b250afd2ba5292e4a6bbd29008e34aa))
* add None check for get_project return in quickstart ([8df6093](https://github.com/nj-io/social-hook/commit/8df60936b2787eda7b55c3f5a88fb3eb895db5b3))
* CLI bugs, dead flags, and flag inconsistencies ([b7baf01](https://github.com/nj-io/social-hook/commit/b7baf01692af1aa81e885a849e9a7565fe2a7f87))
* emit project event after platform_introduced + fix TS identity types ([16c9924](https://github.com/nj-io/social-hook/commit/16c9924ab504747f727fed9970daf2276638978f))
* landing page copy updates and animation fixes ([03e0562](https://github.com/nj-io/social-hook/commit/03e05625c6485fa186c2d15b3fd106da7e24c342))
* make docs logo link back to main site homepage ([ad9048c](https://github.com/nj-io/social-hook/commit/ad9048cba00d8faea32c6e4b1e856dd5ba17f5cd))
* quickstart modal task tracking, ref_id collision, and UI polish ([a734099](https://github.com/nj-io/social-hook/commit/a734099bf3c547b41d4d4f94e6633aa3ee6b8947))
* remove unused update_draft import after merge ([ea992a1](https://github.com/nj-io/social-hook/commit/ea992a17165d5c03d0f015be32a99e44cf10f60f))
* resolve lint and typecheck CI failures ([1937cf9](https://github.com/nj-io/social-hook/commit/1937cf9398b455c4a2a1aa013f2bb485e2c351d1))
* resolve lint and typecheck CI failures ([#27](https://github.com/nj-io/social-hook/issues/27)) ([4600f37](https://github.com/nj-io/social-hook/commit/4600f3717702f49b2b0c8748388f3c87068c56c4))
* resolve mypy no-any-return in adapter registry ([669ed04](https://github.com/nj-io/social-hook/commit/669ed0459841c81a141dbe6647bc2cd56c7f5f08))
* show (active) label on "All branches" when no trigger_branch set ([f90c3ea](https://github.com/nj-io/social-hook/commit/f90c3eabad13d1c3dc6f8fb3a3f2fc42c250074b))
* type annotate button handlers dict to fix mypy dict-item errors ([269693b](https://github.com/nj-io/social-hook/commit/269693b4a9ad9f190ff58233d4a093291df24089))
* update wizard tests for new setup flow and renamed discover_providers ([2559e39](https://github.com/nj-io/social-hook/commit/2559e39454aa421826252c298b747657060af094))
* wizard UI polish — fixed nav, centered stepper, smart credentials ([6261f79](https://github.com/nj-io/social-hook/commit/6261f79d481316642bb508e9fd6525e6183db0f4))


### Documentation

* add conceptual guides for pipeline, arcs, voice memory, and media ([ccf47ad](https://github.com/nj-io/social-hook/commit/ccf47adfc435e4d41405357b1011f18d58efe861))
* add Contributor Covenant v2.1 Code of Conduct ([c65f478](https://github.com/nj-io/social-hook/commit/c65f478f4ca177883fda6a1c6b036ec87290eeab))
* add full configuration reference extracted from code ([a165187](https://github.com/nj-io/social-hook/commit/a16518714d0dc78de15acc850b28b648bff03c7f))
* overhaul README to reflect current product state ([6315e76](https://github.com/nj-io/social-hook/commit/6315e76ed18b257482d3d4ca41d5c46ea51729a6))

## [0.9.0](https://github.com/nj-io/social-hook/compare/social-hook-v0.8.0...social-hook-v0.9.0) (2026-03-13)


### Features

* OSS publish prep — docs site, CLI fixes, community files ([62a4343](https://github.com/nj-io/social-hook/commit/62a43436699504b7224e4e68d68624c5814fb608))
* update docs for new CLI commands, add coverage badge ([514dae3](https://github.com/nj-io/social-hook/commit/514dae3be612269ab6443977938e67dc021f112d))


### Bug Fixes

* add forgiving --json flag to rate-limits command ([25266cd](https://github.com/nj-io/social-hook/commit/25266cdce6ae111e2058b04ad66d130ef89e2674))
* add forgiving --json flag to rate-limits command ([836b3e4](https://github.com/nj-io/social-hook/commit/836b3e486b250afd2ba5292e4a6bbd29008e34aa))
* make docs logo link back to main site homepage ([ad9048c](https://github.com/nj-io/social-hook/commit/ad9048cba00d8faea32c6e4b1e856dd5ba17f5cd))


### Documentation

* add Contributor Covenant v2.1 Code of Conduct ([c65f478](https://github.com/nj-io/social-hook/commit/c65f478f4ca177883fda6a1c6b036ec87290eeab))
* overhaul README to reflect current product state ([6315e76](https://github.com/nj-io/social-hook/commit/6315e76ed18b257482d3d4ca41d5c46ea51729a6))

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
