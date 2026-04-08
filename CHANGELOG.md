# Changelog

## [0.12.0](https://github.com/nj-io/social-hook/compare/v0.11.0...v0.12.0) (2026-04-03)


### Features

* --headless flag, inline re-auth, token DB fixes, faster SSE test ([5a492df](https://github.com/nj-io/social-hook/commit/5a492df27f1fc957284329866c8c34edc2dcf27a))
* ✨ add Analysis Queue card on project page ([7a405d0](https://github.com/nj-io/social-hook/commit/7a405d056e3f3ff0d468dde82b2c9034ffadfce3))
* ✨ add Delete button to targets section ([4c34e27](https://github.com/nj-io/social-hook/commit/4c34e27b6ef4429fa9fc20e6e7ee3065521916ed))
* ✨ add evaluation inspection helper for E2E tests ([43e8bae](https://github.com/nj-io/social-hook/commit/43e8bae7d1316b438060cd0e9ca1fb08ad1830f6))
* ✨ add time simulation helper for E2E tests ([fe4070e](https://github.com/nj-io/social-hook/commit/fe4070e875c457d952c7868e3b95b737ec7346cf))
* ✨ batch evaluation refactor + settings project selector + commit log ([02c21fc](https://github.com/nj-io/social-hook/commit/02c21fc4ad4a1d758a1bdf6d058835f6f0b243ce))
* ✨ evaluation cycle status count links to drafts page ([c6b31b1](https://github.com/nj-io/social-hook/commit/c6b31b171cd3b6abd13229685cd3ac833aa06e6c))
* ✨ event log on System page with collapsible sections ([5cf93d2](https://github.com/nj-io/social-hook/commit/5cf93d22c013921bcdbaca5b1971b51f8228adda))
* ✨ frontend tracks bot LLM tasks — stage labels + error handling ([e5b863b](https://github.com/nj-io/social-hook/commit/e5b863ba2edcf01ea025b180d86fc9d1c3b42298))
* ✨ import history limit — restrict number of commits imported ([74e29a0](https://github.com/nj-io/social-hook/commit/74e29a0d9cb19566075ce6b7d4b6a1a32b89e8cf))
* ✨ import limit in UI modal + reasoning expands on row click ([862f50c](https://github.com/nj-io/social-hook/commit/862f50c34c9ee035eab84579aaa8420f109cbb17))
* ✨ LLM-based strategy type classification for custom strategies ([273224f](https://github.com/nj-io/social-hook/commit/273224f492e57eb93a51b59a454951f915d2ee0c))
* ✨ migrate bot LLM calls to background tasks with stage tracking ([f5b6654](https://github.com/nj-io/social-hook/commit/f5b66542f352e93e2f3106feed96ced2980ac923))
* ✨ multi-strategy wizard selection + CLI quickstart flags ([ed6f146](https://github.com/nj-io/social-hook/commit/ed6f146a3429a39a873edc3827685a36340939ec))
* ✨ nav bar activity indicator — pulsing dot during LLM work ([292e7eb](https://github.com/nj-io/social-hook/commit/292e7eb8bc3639451297b95138a5b095a175dab9))
* ✨ phase 1 — cycle notifications, CLI draft-now, topic_commits, tab persistence ([d89bb36](https://github.com/nj-io/social-hook/commit/d89bb36b2f08e369581d90403c5fcb2b53050b4f))
* ✨ phase 2 — evaluation cycles UI (inline actions, holds, timestamps) ([28d6797](https://github.com/nj-io/social-hook/commit/28d679721642b6a8af4d4210c3e4380e524dda98))
* ✨ phase 3 — CRUD endpoints, CLI parity, topic/suggestion UI ([44d5483](https://github.com/nj-io/social-hook/commit/44d5483c9f8dda61b5f45d514c85b15d4ecfa907))
* ✨ phase 4 — per-strategy posting state, topic queue context, constraint validation ([caa9c2c](https://github.com/nj-io/social-hook/commit/caa9c2cb1aba7fcf459db1ad4b6f362ef523b065))
* ✨ phase 5a+5d — commit analyzer, post metadata population ([1b962e2](https://github.com/nj-io/social-hook/commit/1b962e239ed45d35b20caaeac814f554f34dbb66))
* ✨ phase 5b — evaluator restructure, trivial skip, classification badges ([dde3c0d](https://github.com/nj-io/social-hook/commit/dde3c0d6ae574c01d6ff49b0060b976c14f69a61))
* ✨ phase 5c — deep context assembly (real file diffs, topic commits) ([891256b](https://github.com/nj-io/social-hook/commit/891256be388e3b776663d37ef7e125699b5f4a3f))
* ✨ phase 6 — per-account gap, topic status, queue notifications, error feed, tag filtering ([68a4af1](https://github.com/nj-io/social-hook/commit/68a4af1e0f921e290b51ce61f3a014a670e391a8))
* ✨ pipeline diagnostics system — structured health checks ([ed39b66](https://github.com/nj-io/social-hook/commit/ed39b666a08ec3fb5ac092650136be8647e72171))
* ✨ pipeline stage events + processing status + Create Draft AsyncButton ([925c21c](https://github.com/nj-io/social-hook/commit/925c21c4bfe6c778a06ab4d5a67f7aa470b22cec))
* ✨ preview drafts for strategies without targets ([260a703](https://github.com/nj-io/social-hook/commit/260a70315a43a6534fd9d193ace5482e58968a30))
* ✨ preview mode on real platforms, strategy wiring, shared-group drafting ([218f769](https://github.com/nj-io/social-hook/commit/218f769097654980fd311f3c9dbdf137768dd485))
* ✨ reusable task stage tracking — per-stage progress on UI elements ([d865600](https://github.com/nj-io/social-hook/commit/d86560026dc13ebc41b3f887242621b47b7ecf21))
* ✨ system error clear + 30-day TTL pruning ([4898693](https://github.com/nj-io/social-hook/commit/4898693d4e23fb108ec2dbf10b3f2bb9287e4ffd))
* ✨ targets system — full implementation with two-stage evaluation, topic queue, and UI ([a4ee0a9](https://github.com/nj-io/social-hook/commit/a4ee0a9e16da8531b4022df2f626a36cf9533039))
* ✨ topic-drafter flow fixes, batch evaluate endpoint, commit log UX ([8bc081f](https://github.com/nj-io/social-hook/commit/8bc081f30065892f070e2734b450fca6c1195abc))
* ✨ two-stage evaluation fix, topic queue overhaul, UI gaps ([d804a49](https://github.com/nj-io/social-hook/commit/d804a49262e8d87e29ecf45dfc7be958535b4641))
* ✨ unified logging pipeline with multi-sink LogBus ([c4496d9](https://github.com/nj-io/social-hook/commit/c4496d98d111a0477d446c537de90b30790434e0))
* ✨ wizard branch selector, stepper overflow fix, error toast persistence ([e063fb1](https://github.com/nj-io/social-hook/commit/e063fb1fcc7d0b92a36d4ddde053deb0e60cf406))
* add --set flag to credentials add for non-interactive agent/CI use ([9292fd9](https://github.com/nj-io/social-hook/commit/9292fd99b8d7ff139717e74ab5afc3a5164a96e2))
* add reusable maintenance loop agent and docs config ([caa1d54](https://github.com/nj-io/social-hook/commit/caa1d542ce8bd0415fdff8a29036a0ddc7a28c47))
* headless E2E, inline re-auth, Basic Auth refresh fix ([9b873bf](https://github.com/nj-io/social-hook/commit/9b873bf0f40093b3d8c5abef921220dc75ed308a))
* OAuth 2.0 migration, generic web OAuth, E2E overhaul ([5f88624](https://github.com/nj-io/social-hook/commit/5f88624606ce85f9751670e2cb1be093b83300d1))
* targets system — evaluation, topics, settings, wizard ([c836822](https://github.com/nj-io/social-hook/commit/c83682225a7d212853716a96154b22a18b9a046f))
* targets system, preview mode, OAuth 2.0 migration ([4e955dd](https://github.com/nj-io/social-hook/commit/4e955dd9d5a270784afc639e69e369d89edbe955))
* unified logging pipeline with multi-sink LogBus ([4a42d82](https://github.com/nj-io/social-hook/commit/4a42d828140e0c8368c08e9e0a9004e3c02c9b67))


### Bug Fixes

* ✨ error copy button + activity indicator shows on page refresh ([c815cb7](https://github.com/nj-io/social-hook/commit/c815cb772b6ffd1eaad92ef1514d33b306fe7d03))
* 🐛 activity indicator — center in nav, only visible during work ([218b57a](https://github.com/nj-io/social-hook/commit/218b57a2f18374c2d2e29269c9f437b9e13dcd43))
* 🐛 activity indicator only tracks task lifecycle, not pipeline stages ([9a76a15](https://github.com/nj-io/social-hook/commit/9a76a1590f8df7a307558c31ad17a65a9b55ad08))
* 🐛 add dismissed status to content_topics CHECK constraint ([bd380f7](https://github.com/nj-io/social-hook/commit/bd380f72d06335c5bffce717e7322235932cc459))
* 🐛 add EVALUATING to DecisionType enum (model validation crash) ([53cc931](https://github.com/nj-io/social-hook/commit/53cc9311b7cd60177a514aa998d1c153c3f7223d))
* 🐛 add logging to _run_commit_analyzer gating + fix stale docstring ([3820042](https://github.com/nj-io/social-hook/commit/38200429b63961167cfa835c58fb7486706a03f8))
* 🐛 analysis queue card text at threshold (3/3 = evaluating) ([942f237](https://github.com/nj-io/social-hook/commit/942f237db05f480e4aa770684b72374b24ea6566))
* 🐛 analysis queue card text, remove duplicate project summary ([9afe317](https://github.com/nj-io/social-hook/commit/9afe31747b7b1a0b11495c18179f8eedb6a55f21))
* 🐛 batch evaluate parallel, cycle strategies without drafts ([add3783](https://github.com/nj-io/social-hook/commit/add37836c9a30ff203b3bf2b928e8fc5d1009ea1))
* 🐛 batch evaluate separates trigger from deferred, reuses existing decision ([6fa262e](https://github.com/nj-io/social-hook/commit/6fa262ec71cbe27cc720a67924b36f9328b0f744))
* 🐛 batched decisions show "Batched" badge + cycle ID cross-reference ([94f972a](https://github.com/nj-io/social-hook/commit/94f972aad49e4f5781ada71b823adf8ad0c88457))
* 🐛 commit log UX — per-row loading, background task evaluate, context labels ([ea7072f](https://github.com/nj-io/social-hook/commit/ea7072f978293c1c476704655ed339aca986f9cd))
* 🐛 context config saves to project config, not global ([e223ac2](https://github.com/nj-io/social-hook/commit/e223ac2ce26c7715040243a5fad883dd00e2d477))
* 🐛 credentials validate text output — iterate directly, no type cast ([5dac46e](https://github.com/nj-io/social-hook/commit/5dac46e328605da7a447b4406d208db03fc68aa6))
* 🐛 dead code, misleading name, double polling ([ab3c768](https://github.com/nj-io/social-hook/commit/ab3c7689ceedb892dedb8d64f28db5951ab93e28))
* 🐛 don't set reasoning on evaluating decisions, clear on startup ([72e4ee0](https://github.com/nj-io/social-hook/commit/72e4ee03860e9d1f018ff0103905b02958fd95c5))
* 🐛 drain tests patch create_client for CI (no API key) ([b4b7fda](https://github.com/nj-io/social-hook/commit/b4b7fda49b3d3792b3e285235611c75039feea18))
* 🐛 enrich batch evaluation trigger description in cycles view ([183f160](https://github.com/nj-io/social-hook/commit/183f160b24a197a8686a93bdd1886fd7fc4768ae))
* 🐛 enrich evaluation cycles API, use AsyncButton for evaluate ([f5d8e9e](https://github.com/nj-io/social-hook/commit/f5d8e9edd311570f39bc59542ef25858499e08a9))
* 🐛 evaluate button loading persists via background task tracking ([60ed2d9](https://github.com/nj-io/social-hook/commit/60ed2d9176ac063b05b4551a0e234191fa0b588a))
* 🐛 evaluate in-place via upsert, stale task cleanup, timestamp Z suffix ([0d468cd](https://github.com/nj-io/social-hook/commit/0d468cd71f4236b2478ed4b2b47d91da8a7e68dc))
* 🐛 evaluator schema told LLM to use 'default' strategy key ([5bddd81](https://github.com/nj-io/social-hook/commit/5bddd81a85c375b6d7bd0cc8a854c52c999816d3))
* 🐛 first commit respects analysis queue interval like any other ([4f9a335](https://github.com/nj-io/social-hook/commit/4f9a33584cf05ec449c11579d2484e53d7f76713))
* 🐛 handlePromote tracks background task instead of clearing immediately ([e176aa9](https://github.com/nj-io/social-hook/commit/e176aa912968dfd3710a3291535b1f1868586892))
* 🐛 import modal branch dropdown uses git branches, not decision history ([ea2bc37](https://github.com/nj-io/social-hook/commit/ea2bc373552f914688388b706b32f1830764f565))
* 🐛 import modal polls for completion instead of relying on WebSocket ([3973074](https://github.com/nj-io/social-hook/commit/3973074be8733e40c0606ebb2f119aba69af924a))
* 🐛 import task ref_id mismatch — modal never closes ([782318d](https://github.com/nj-io/social-hook/commit/782318dde267a620f324894337d99d1fe35048cf))
* 🐛 include processed field in Decision.to_row() and INSERT statements ([9ce5a50](https://github.com/nj-io/social-hook/commit/9ce5a503e287383ab57a033dca624437806e638a))
* 🐛 initialize error feed at web startup, emit on task failure ([2b04f1f](https://github.com/nj-io/social-hook/commit/2b04f1f646b0422b778be478b706a6b433447fa2))
* 🐛 last mypy error in credentials.py ([5aa615b](https://github.com/nj-io/social-hook/commit/5aa615bd941175aeff3279e50e74f92c8f3e59f7))
* 🐛 Lifecycle.from_dict default={} should be default=[] ([c7fb04e](https://github.com/nj-io/social-hook/commit/c7fb04e36d226a4d0b44e59e8046608f91df27e9))
* 🐛 manual retrigger bypasses trigger_branch check ([a92b204](https://github.com/nj-io/social-hook/commit/a92b204d71fa7ae819042d9d75cdd23ffd3b5485))
* 🐛 move settings controls to relevant sections ([e1e8899](https://github.com/nj-io/social-hook/commit/e1e8899c3e2742472514b5c6018504fdd70ed3ed))
* 🐛 mypy type errors, regenerate CLI docs for new commands ([47a5c61](https://github.com/nj-io/social-hook/commit/47a5c61552615e91d54a0416590cb27bc6f198db))
* 🐛 mypy type ignore for credentials missing_keys ([052d4cc](https://github.com/nj-io/social-hook/commit/052d4cc634b71afcab89199dfd90f40da02ec1a9))
* 🐛 paid tier prompt encourages rich single posts over threads ([0251030](https://github.com/nj-io/social-hook/commit/0251030d0b3b95a803d38b23bdc6aa59d1593e2f))
* 🐛 pattern compliance — config parser, connection leaks, silent catches ([1f787db](https://github.com/nj-io/social-hook/commit/1f787dbd2e9966fa00f412a5507d0e01ea94cd7c))
* 🐛 pipeline flow fixes — 8 issues from batch evaluation testing ([ec5712d](https://github.com/nj-io/social-hook/commit/ec5712db73d66855bac67807b048ab1f2d883c9d))
* 🐛 PRAGMA migration parser misclassifies when comments precede PRAGMA ([a1b9e9c](https://github.com/nj-io/social-hook/commit/a1b9e9c31af7fa601be9ead0cca1307c27bb0ef2))
* 🐛 preserve original branch on retrigger/drain, scope import to trigger branch ([1ff3f7b](https://github.com/nj-io/social-hook/commit/1ff3f7bb8b87fe9d646e416e4bfb98681b02172c))
* 🐛 prevent recursive logging loop in DbSink ([d541ba8](https://github.com/nj-io/social-hook/commit/d541ba8a2180ce8d12847b1c08c56cb9ebf505d3))
* 🐛 preview drafts respect platform tier, shared group uses single-call variants ([4a596db](https://github.com/nj-io/social-hook/commit/4a596db4e8848b61f38a76d79c35ed6e1cc15b7a))
* 🐛 preview_mode checks account-level OAuth credentials ([0969dec](https://github.com/nj-io/social-hook/commit/0969dec888770755d45ea56798a678e7df88e911))
* 🐛 preview_mode checks OAuth credentials, not just account existence ([02604f1](https://github.com/nj-io/social-hook/commit/02604f1f299efbcbaac4966d83f7852ca33c9afb))
* 🐛 reasoning + angle columns use ExpandableText, remove 500-char truncation ([ea7bf8f](https://github.com/nj-io/social-hook/commit/ea7bf8f80869922a68c3104aac441decdee354a9))
* 🐛 reasoning column shows full text on expand, remove duplicate from commit column ([f34927c](https://github.com/nj-io/social-hook/commit/f34927c0c7b782543cdf558433cbaab20a952ae1))
* 🐛 remaining mypy errors and hardcoded test path ([260a3d3](https://github.com/nj-io/social-hook/commit/260a3d3fc6007b3c60ba7271558c81e9cabde284))
* 🐛 replace window.confirm with Modal for destructive actions ([711a25d](https://github.com/nj-io/social-hook/commit/711a25dd673b1a20dc442b74b0d26ebb0a183477))
* 🐛 resolve all mypy errors (30 → 0) ([ebd7b67](https://github.com/nj-io/social-hook/commit/ebd7b67dfae1c4fe757131702b7fbabf6624b1d9))
* 🐛 resolve mypy errors from reusability refactor ([35b8c7a](https://github.com/nj-io/social-hook/commit/35b8c7aa1f548920a9174f09af681aa3d296e2e4))
* 🐛 settings dict-to-array conversion, React 0-render gotcha, stale OAuth test ([0afd1a0](https://github.com/nj-io/social-hook/commit/0afd1a05e0673c1dfcc2ed94324827561cbcb204))
* 🐛 settings sections update when project added/removed ([f6c254b](https://github.com/nj-io/social-hook/commit/f6c254bf771c063686810ce0f6544682a0b78bac))
* 🐛 settings shows "register project first" when no project exists ([2b4938d](https://github.com/nj-io/social-hook/commit/2b4938d68e85066faea59ff3d04f8040da10b02a))
* 🐛 show strategy outcomes in cycles even without drafts ([91935c9](https://github.com/nj-io/social-hook/commit/91935c9fb197b0852380e77c09274070daa143a4))
* 🐛 simplify logging — double prefix, dead code, thread cap ([3ae2cb6](https://github.com/nj-io/social-hook/commit/3ae2cb6d3f0d472ff6ebb93539404014b463c9c9))
* 🐛 simplify pass 2 — naive datetime guard, remove wasted query ([65bdb7f](https://github.com/nj-io/social-hook/commit/65bdb7f0c890b316c73179becc34d871dc43c988))
* 🐛 simplify pass 3 — XSS fix, remove dead wrapper, cleanup ([f3e1e1f](https://github.com/nj-io/social-hook/commit/f3e1e1fe7fa712fd177aa466e5a510e058c9fab8))
* 🐛 simplify pass 4 — connection leak, enum_value consistency, dead code ([508441c](https://github.com/nj-io/social-hook/commit/508441cddaaa8a13626b156a688f91f653f22047))
* 🐛 simplify pass 4 round 2 — enum_value consistency, skip redundant fetch ([5e85740](https://github.com/nj-io/social-hook/commit/5e857403eab9c263359ed60190059af1d3c80c39))
* 🐛 stale task cleanup uses DecisionType enum, not hardcoded strings ([3add077](https://github.com/nj-io/social-hook/commit/3add077452ff5cdb532d4da77804ba79744d89e3))
* 🐛 strategies list shows built-in templates merged with config ([b97d06a](https://github.com/nj-io/social-hook/commit/b97d06a21bc86167f76f840a9294a951efe9a5d1))
* 🐛 suppress bulk topic creation toasts during evaluation ([68b6d2c](https://github.com/nj-io/social-hook/commit/68b6d2c880323d436681d9c2eaae4c9d48f530ae))
* 🐛 target disable, account remove, credential remove buttons ([52d5afd](https://github.com/nj-io/social-hook/commit/52d5afdcee1559aa8b4db5f40a3201388f01fa4d))
* 🐛 target disable/enable writes full data from Config object ([9cc68fa](https://github.com/nj-io/social-hook/commit/9cc68fa43f74566d5dd5538f1bd45bbce65f5477))
* 🐛 target enable persists — drop deep_merge on disable/enable ([2cc556a](https://github.com/nj-io/social-hook/commit/2cc556a75f6143b9a4b3c1fc83de96e8a87260d0))
* 🐛 target strategy validation accepts built-in templates, fix name collision ([31b82c5](https://github.com/nj-io/social-hook/commit/31b82c5aca14b153177a2c5a78cd905886a79a6b))
* 🐛 text prompt stays visible during background task processing ([bd4e4b9](https://github.com/nj-io/social-hook/commit/bd4e4b99c11a11d6069482b04dc00ccd5a1dc743))
* 🐛 trigger decision gets batch_id + content_source rendered safely ([59cc13a](https://github.com/nj-io/social-hook/commit/59cc13ab760abd520a1269b9929421877fd4d9c3))
* 🐛 wire on_persist in all processes for cross-process WebSocket updates ([9bb41bc](https://github.com/nj-io/social-hook/commit/9bb41bcac3b73d38a93903f438f6818911f8beec))
* 🐛 wizard stepper equal gaps via CSS contents layout ([774041a](https://github.com/nj-io/social-hook/commit/774041a3981c500e0f48937e13778f87a9b7b954))
* accurate scroll-to-section positioning in settings ([c8b0446](https://github.com/nj-io/social-hook/commit/c8b0446c19d27c17d89b974ce770560d6997ce89))
* activity indicator absolute center of navbar ([6fe935f](https://github.com/nj-io/social-hook/commit/6fe935f05a0e9ee8cb32d6aa7ace9ac39f63918e))
* add task stage tracking to evaluate_batch in trigger_batch.py ([146eab2](https://github.com/nj-io/social-hook/commit/146eab283f08590e57f1dd89af2239a631aba74d))
* CI failures — regenerate CLI docs, fix mypy return type ([b845e24](https://github.com/nj-io/social-hook/commit/b845e2456642696f35bb7565043e7bc4bf87d658))
* **docs-maintenance:** clarify step 1 — always branch from latest target branch ([58a7a78](https://github.com/nj-io/social-hook/commit/58a7a78c9f600959129d6e20ced73bb5841253f3))
* mypy type ignore for _dispatch_chat_message return ([c4227b6](https://github.com/nj-io/social-hook/commit/c4227b651a57978600219cf6a9200738913f35e7))
* override notification fixture for tests that verify notification paths ([b25ad18](https://github.com/nj-io/social-hook/commit/b25ad18579e213aee021e2d4d5b72d2a2f3301c5))
* prevent recursive logging loop in DbSink ([ed2ceac](https://github.com/nj-io/social-hook/commit/ed2ceacfc7a649eb226d5adcc3ec790cba6a0def))
* prevent tests from sending real notifications ([5d0d3f4](https://github.com/nj-io/social-hook/commit/5d0d3f4eb3a158dbb047f6552f82cb6c1b1312f1))
* prevent tests from sending real notifications ([b25869e](https://github.com/nj-io/social-hook/commit/b25869e5f3b12e245d5c40ac61232761dddc1bcc))
* restore no-truncation policy for strategy reasoning ([1cf713f](https://github.com/nj-io/social-hook/commit/1cf713f9e4d546ff23e35a495fb6c023f2060b4f))
* stub broadcast_notification instead of send_notification ([b4f9aae](https://github.com/nj-io/social-hook/commit/b4f9aae0014c9025dbb7d5feb2187831bf9ec417))
* stub broadcast_notification instead of send_notification ([4c571b2](https://github.com/nj-io/social-hook/commit/4c571b2e25413c4acab8bdaeec9dea93938728b4))
* use Basic Auth for token refresh (matches code exchange) ([8b7b5f5](https://github.com/nj-io/social-hook/commit/8b7b5f51d6517abcd44a8dcf3d031e8e624a50d8))
* use getBoundingClientRect for accurate scroll-to-section positioning ([9f39122](https://github.com/nj-io/social-hook/commit/9f39122b5b10361e93ad49d00afe92e4fa45236e))
* wire ActivityIndicator into nav bar ([5846757](https://github.com/nj-io/social-hook/commit/5846757510c3828be963aa893a7e21309aa41f10))


### Performance

* ⚡ move interval gating before expensive pipeline work ([6444ee2](https://github.com/nj-io/social-hook/commit/6444ee244941158646c35d4bc6700b7b63e06282))


### Documentation

* add --yes examples to all commands with confirmation prompts ([71df5ec](https://github.com/nj-io/social-hook/commit/71df5ec591b6a8b415070b49202f7766be2f2d94))
* add Recurring Checks section to DOC_STATUS.md ([01da4c9](https://github.com/nj-io/social-hook/commit/01da4c97822912e96639483d26c6d9657e94ce67))
* add testing and E2E docs to backlog ([214c36e](https://github.com/nj-io/social-hook/commit/214c36ec729133a9b7dceeec7a03cd5e446f8d1d))
* CLI reference regenerated ([68a4af1](https://github.com/nj-io/social-hook/commit/68a4af1e0f921e290b51ce61f3a014a670e391a8))
* daily maintenance loop — merge develop, fix nav + preview mode ([68c7c28](https://github.com/nj-io/social-hook/commit/68c7c28e67a2d3fe3804fa74bdcf0584c4ddb532))
* daily maintenance loop — update tracking to current HEAD ([5c57c1c](https://github.com/nj-io/social-hook/commit/5c57c1ced0f3e8b1b8e00531e2fefb1370efdffe))
* daily maintenance loop — update tracking, correct getting-started status ([0a5c88f](https://github.com/nj-io/social-hook/commit/0a5c88fe612159a365b12737a493974dc5d43c7c))
* daily maintenance loop — update tracking, upgrade setup status ([dcf5550](https://github.com/nj-io/social-hook/commit/dcf5550af38e21b3fdcdba51efa96f35e19bbb9c))
* enrich 16 CLI command docstrings (inspect, decision, manual, draft, strategy, target) ([73e6d5e](https://github.com/nj-io/social-hook/commit/73e6d5eda1719303bdf3adbef72aa4cdcc8b615a))
* enrich CLI docstrings and add DOC_STATUS tracking ([f07f521](https://github.com/nj-io/social-hook/commit/f07f52124396725fc2b848897c3c1587c8f237c5))
* enrich CLI docstrings and add DOC_STATUS tracking ([a4ff197](https://github.com/nj-io/social-hook/commit/a4ff197c05a7125ff90f047c2bc10efc60a6c3a4))
* enrich group-level help text for 9 new CLI command groups ([46e4587](https://github.com/nj-io/social-hook/commit/46e45874e98bbcea6678feac6c0de5bc0d8d98c4))
* incorporate site-docs staleness audit findings ([9c283a6](https://github.com/nj-io/social-hook/commit/9c283a662bfbdbade15d83702f3871587055363a))
* refine DOC_STATUS coverage from CLI docstring audit ([103940a](https://github.com/nj-io/social-hook/commit/103940afe05e0d7e9adb3da97dd6f6eb9b2cf896))
* regenerate CLI reference docs with enriched docstrings ([ded996a](https://github.com/nj-io/social-hook/commit/ded996a06e5018f9bfff5585a6e6143cb9f52510))
* rewrite pipeline.md for two-stage evaluation and targets ([4d94d18](https://github.com/nj-io/social-hook/commit/4d94d1845a090a60c97869803fd6da66588cf023))
* update DOC_STATUS — mark 9 CLI groups as enriched ([4a13bcc](https://github.com/nj-io/social-hook/commit/4a13bcc1fe3983b77cedac045446171716428810))
* update DOC_STATUS — mark completed items, add recurring checks ([4c25bc2](https://github.com/nj-io/social-hook/commit/4c25bc2ca77bf63a6585c5c0e6a2103b98009762))
* update narrative-arcs.md for strategy-scoped arcs and episode tags ([8363d45](https://github.com/nj-io/social-hook/commit/8363d4545618a4fe4925c67513235715f6221178))

## [0.11.0](https://github.com/nj-io/social-hook/compare/v0.10.0...v0.11.0) (2026-03-24)


### Features

* ✨ defensive programming — structural fixes and prevention utilities ([5934202](https://github.com/nj-io/social-hook/commit/59342021735e305027ed73d795b13e4d5d828081))
* add --pause flag to E2E platform posting tests ([9e25d38](https://github.com/nj-io/social-hook/commit/9e25d387675483823adc21f20ec0e83b0d0da904))
* add MkDocs hook to inject version from pyproject.toml ([c11dae5](https://github.com/nj-io/social-hook/commit/c11dae5aa364bbc00eb2501c56aaf19cb334ece2))
* defensive programming — structural fixes and prevention utilities ([856eb81](https://github.com/nj-io/social-hook/commit/856eb81ef2479bbb8a947f8a8e71c47e7a076613))
* dynamic version in docs site via MkDocs hook ([21c6a1f](https://github.com/nj-io/social-hook/commit/21c6a1ffe50cdf762497b4b5c0b0879ddc1fdc56))
* platform posting capabilities, E2E harness, and post-now action ([a87fa62](https://github.com/nj-io/social-hook/commit/a87fa627754c276ace0c14463f5b7c28a249f2d6))


### Bug Fixes

* 🐛 background task race condition and client-side timeout ([72b9903](https://github.com/nj-io/social-hook/commit/72b9903fea6bd3ca5cc628ec6535f7fe78d0ca65))
* 🐛 mypy errors in consolidation return type and scheduling variable shadow ([3892f88](https://github.com/nj-io/social-hook/commit/3892f88062355c14204e5858216581ef55b9111c))
* add return type annotation to _tick_single_draft ([b84a040](https://github.com/nj-io/social-hook/commit/b84a0404c410fe2d2c55fe01925eed60bb945acd))


### Documentation

* regenerate CLI docs to match current commands ([04d954c](https://github.com/nj-io/social-hook/commit/04d954ce6b40343356a96446e638701a9cf36a4e))

## [0.10.0](https://github.com/nj-io/social-hook/compare/v0.9.0...v0.10.0) (2026-03-21)


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
