"""Tests for configuration functionality (T2, T9, T20d)."""

import pytest

from social_hook.config import load_config, load_env, load_full_config, load_project_config
from social_hook.config.project import (
    DEFAULT_MEDIA_GUIDANCE,
    ContextConfig,
    EpisodePreferences,
    StrategyConfig,
    SummaryConfig,
    _parse_context_config,
    _parse_media_guidance,
    _parse_strategy_config,
    _parse_summary_config,
    save_memory,
)
from social_hook.constants import CONFIG_DIR_NAME
from social_hook.errors import ConfigError

# =============================================================================
# T2: Config Loading
# =============================================================================


class TestEnvLoading:
    """T2: Environment variable loading tests."""

    def test_load_valid_env(self, temp_env_file):
        """Load valid .env returns dict with all keys."""
        env = load_env(temp_env_file)
        assert "ANTHROPIC_API_KEY" in env
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-test-key"
        assert env["TELEGRAM_BOT_TOKEN"] == "123456:ABC"

    def test_load_env_without_any_keys_succeeds(self, temp_dir):
        """load_env() succeeds with no API keys (no required keys)."""
        env_path = temp_dir / ".env"
        env_path.write_text("TELEGRAM_BOT_TOKEN=123456:ABC\n")

        env = load_env(env_path)
        assert env["TELEGRAM_BOT_TOKEN"] == "123456:ABC"

    def test_load_env_with_quotes(self, temp_dir):
        """Load .env with quoted values handles quotes correctly."""
        env_path = temp_dir / ".env"
        env_path.write_text(
            """\
ANTHROPIC_API_KEY="sk-ant-quoted-key"
X_API_KEY='single-quoted'
"""
        )

        env = load_env(env_path)
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-quoted-key"
        assert env["X_API_KEY"] == "single-quoted"

    def test_load_env_with_comments(self, temp_dir):
        """Load .env skips comments and empty lines."""
        env_path = temp_dir / ".env"
        env_path.write_text(
            """\
# This is a comment
ANTHROPIC_API_KEY=sk-ant-key

# Another comment
TELEGRAM_BOT_TOKEN=123456:ABC
"""
        )

        env = load_env(env_path)
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-key"
        assert env["TELEGRAM_BOT_TOKEN"] == "123456:ABC"


class TestYamlLoading:
    """T2: YAML config loading tests."""

    def test_load_valid_config(self, temp_config_file):
        """Load valid config.yaml returns Config object."""
        config = load_config(temp_config_file)

        assert config.models.evaluator == "anthropic/claude-opus-4-5"
        assert config.models.drafter == "anthropic/claude-sonnet-4-5"
        assert config.models.gatekeeper == "anthropic/claude-haiku-4-5"
        assert config.platforms["x"].enabled is True
        assert config.platforms["x"].account_tier == "free"
        assert config.scheduling.timezone == "America/Los_Angeles"

    def test_invalid_model_value(self, temp_dir):
        """Invalid model value raises ConfigError."""
        # Bare name without provider prefix is invalid
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
models:
  evaluator: gpt4
"""
        )

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_path)

        assert "Invalid model 'gpt4'" in str(exc_info.value)

    def test_bare_model_name_invalid(self, temp_dir):
        """Bare model name (no provider prefix) raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
models:
  evaluator: claude-opus-4-5
"""
        )

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_path)

        assert "Invalid model 'claude-opus-4-5'" in str(exc_info.value)

    def test_valid_provider_prefixed_models(self, temp_dir):
        """Provider-prefixed model names are valid."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
models:
  evaluator: anthropic/claude-opus-4-5
  drafter: claude-cli/sonnet
  gatekeeper: anthropic/claude-haiku-4-5
"""
        )

        config = load_config(config_path)
        assert config.models.evaluator == "anthropic/claude-opus-4-5"
        assert config.models.drafter == "claude-cli/sonnet"
        assert config.models.gatekeeper == "anthropic/claude-haiku-4-5"

    def test_missing_config_returns_default(self):
        """Missing config.yaml returns default Config."""
        config = load_config(None)

        assert config.models.evaluator == "anthropic/claude-opus-4-5"
        assert config.models.drafter == "anthropic/claude-opus-4-5"
        assert config.models.gatekeeper == "anthropic/claude-haiku-4-5"

    def test_load_full_config(self, temp_dir):
        """Load full config merges env and yaml."""
        # Create env file
        env_path = temp_dir / ".env"
        env_path.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")

        # Create yaml file
        yaml_path = temp_dir / "config.yaml"
        yaml_path.write_text(
            """\
models:
  evaluator: anthropic/claude-sonnet-4-5
"""
        )

        config = load_full_config(env_path, yaml_path)

        assert config.env["ANTHROPIC_API_KEY"] == "sk-ant-test"
        assert config.models.evaluator == "anthropic/claude-sonnet-4-5"


# =============================================================================
# T9: Per-Project Config
# =============================================================================


class TestProjectConfig:
    """T9: Per-project configuration loading tests."""

    def test_load_social_context(self, temp_project_dir):
        """Load social-context.md from project."""
        config = load_project_config(temp_project_dir)

        assert config.social_context is not None
        assert "Technical but approachable" in config.social_context
        assert "Developers interested in automation" in config.social_context

    def test_load_content_config(self, temp_project_dir):
        """Load content-config.yaml from project."""
        config = load_project_config(temp_project_dir)

        assert config.content_config is not None
        assert config.content_config["platforms"]["x"]["enabled"] is True
        assert config.content_config["platforms"]["x"]["threads"]["max_tweets"] == 5

    def test_load_memories(self, temp_project_dir):
        """Load memories.md from project."""
        config = load_project_config(temp_project_dir)

        assert config.memories is not None
        assert "Too many emojis" in config.memories

    def test_missing_config_files_returns_defaults(self, temp_dir):
        """Missing config files returns defaults, no error."""
        empty_project = temp_dir / "empty-project"
        empty_project.mkdir()

        # Use temp_dir as global_base for test isolation
        empty_global = temp_dir / "empty-global"
        empty_global.mkdir()

        config = load_project_config(empty_project, global_base=empty_global)

        assert config.social_context is None
        assert config.content_config == {}
        assert config.memories is None
        assert config.repo_path == str(empty_project)

    def test_invalid_yaml_raises_error(self, temp_dir):
        """Invalid YAML raises ConfigError with path."""
        project_dir = temp_dir / "bad-project"
        project_dir.mkdir()

        # Create .social-hook subdirectory
        config_dir = project_dir / CONFIG_DIR_NAME
        config_dir.mkdir()

        (config_dir / "content-config.yaml").write_text(
            """\
platforms:
  x:
    enabled: true
    - invalid yaml
"""
        )

        with pytest.raises(ConfigError) as exc_info:
            load_project_config(project_dir)

        assert "content-config.yaml" in str(exc_info.value)

    def test_save_memory_creates_directory(self, temp_dir):
        """save_memory creates .social-hook directory if it doesn't exist."""
        project_dir = temp_dir / "new-project"
        project_dir.mkdir()

        config_dir = project_dir / CONFIG_DIR_NAME
        assert not config_dir.exists(), "Directory should not exist yet"

        save_memory(project_dir, "test context", "test feedback", "draft-001")

        assert config_dir.exists(), "save_memory should create .social-hook directory"
        assert (config_dir / "memories.md").exists(), "memories.md should be created"

    def test_save_memory_appends_entry(self, temp_project_dir):
        """save_memory appends new entry to existing memories.md."""
        config = load_project_config(temp_project_dir)

        save_memory(temp_project_dir, "new context", "new feedback", "draft-002")

        config = load_project_config(temp_project_dir)
        assert "new context" in config.memories
        assert "new feedback" in config.memories
        assert "draft-002" in config.memories


# =============================================================================
# T9: Config Fallback (project → global)
# =============================================================================


class TestConfigFallback:
    """T9: Config fallback from project to global."""

    def test_fallback_to_global(self, temp_dir):
        """Project missing config, global exists → returns global."""
        # Setup global config (global_base IS the .social-hook equivalent)
        global_base = temp_dir / "global-config"
        global_base.mkdir()
        (global_base / "social-context.md").write_text("Global voice")
        (global_base / "content-config.yaml").write_text("platforms:\n  x:\n    enabled: true")

        # Setup empty project (no .social-hook directory)
        project_dir = temp_dir / "project"
        project_dir.mkdir()

        config = load_project_config(project_dir, global_base=global_base)

        assert config.social_context == "Global voice"
        assert config.content_config["platforms"]["x"]["enabled"] is True

    def test_project_overrides_global(self, temp_dir):
        """Both exist → project wins."""
        # Setup global config
        global_base = temp_dir / "global-config"
        global_base.mkdir()
        (global_base / "social-context.md").write_text("Global voice")

        # Setup project config (project uses .social-hook subdirectory)
        project_dir = temp_dir / "project"
        project_config_dir = project_dir / CONFIG_DIR_NAME
        project_config_dir.mkdir(parents=True)
        (project_config_dir / "social-context.md").write_text("Project voice")

        config = load_project_config(project_dir, global_base=global_base)

        assert config.social_context == "Project voice"

    def test_neither_exists_returns_none(self, temp_dir):
        """Neither project nor global exists → returns None/{}."""
        project_dir = temp_dir / "project"
        project_dir.mkdir()
        global_base = temp_dir / "empty-global"
        global_base.mkdir()

        config = load_project_config(project_dir, global_base=global_base)

        assert config.social_context is None
        assert config.content_config == {}

    def test_memories_no_fallback(self, temp_dir):
        """memories.md is project-only, no global fallback."""
        # Setup global with memories (should be ignored)
        global_base = temp_dir / "global-config"
        global_base.mkdir()
        (global_base / "memories.md").write_text("Global memories")

        # Setup empty project
        project_dir = temp_dir / "project"
        project_dir.mkdir()

        config = load_project_config(project_dir, global_base=global_base)

        # Should NOT fall back to global memories
        assert config.memories is None

    def test_invalid_yaml_in_global_raises_error(self, temp_dir):
        """Invalid YAML in global config raises ConfigError."""
        # Setup global with invalid YAML
        global_base = temp_dir / "global-config"
        global_base.mkdir()
        (global_base / "content-config.yaml").write_text(
            """\
platforms:
  x:
    enabled: true
    - invalid yaml
"""
        )

        # Setup empty project (will fall back to global)
        project_dir = temp_dir / "project"
        project_dir.mkdir()

        with pytest.raises(ConfigError) as exc_info:
            load_project_config(project_dir, global_base=global_base)

        assert "content-config.yaml" in str(exc_info.value)

    def test_partial_fallback(self, temp_dir):
        """Project has one file, falls back to global for the other."""
        # Setup global config with both files
        global_base = temp_dir / "global-config"
        global_base.mkdir()
        (global_base / "social-context.md").write_text("Global voice")
        (global_base / "content-config.yaml").write_text("platforms:\n  x:\n    enabled: false")

        # Setup project with only content-config.yaml (not social-context.md)
        project_dir = temp_dir / "project"
        project_config_dir = project_dir / CONFIG_DIR_NAME
        project_config_dir.mkdir(parents=True)
        (project_config_dir / "content-config.yaml").write_text(
            "platforms:\n  x:\n    enabled: true"
        )

        config = load_project_config(project_dir, global_base=global_base)

        # social-context.md falls back to global
        assert config.social_context == "Global voice"
        # content-config.yaml uses project (overrides global)
        assert config.content_config["platforms"]["x"]["enabled"] is True


# =============================================================================
# T20d: Context Configuration
# =============================================================================


class TestContextConfig:
    """T20d: Typed context and strategy config parsing."""

    def test_default_values(self):
        """Config with no context section uses defaults."""
        config = ContextConfig()
        assert config.recent_decisions == 30
        assert config.recent_posts == 15
        assert config.max_tokens == 150000
        assert config.include_readme is True
        assert config.include_claude_md is True
        assert config.max_doc_tokens == 10000

    def test_default_strategy_values(self):
        """Strategy config with no section uses defaults."""
        config = StrategyConfig()
        assert config.narrative_debt_threshold == 3
        assert config.arc_stagnation_days == 14
        assert config.strategy_moment_max_gap_days == 7

    def test_parse_context_from_dict(self):
        """Parse context config from content-config.yaml data."""
        data = {
            "recent_decisions": 50,
            "recent_posts": 20,
            "max_tokens": 200000,
            "include_readme": False,
            "include_claude_md": False,
            "max_doc_tokens": 5000,
        }
        config = _parse_context_config(data)
        assert config.recent_decisions == 50
        assert config.recent_posts == 20
        assert config.max_tokens == 200000
        assert config.include_readme is False
        assert config.include_claude_md is False
        assert config.max_doc_tokens == 5000

    def test_parse_strategy_from_dict(self):
        """Parse strategy config from content-config.yaml data."""
        data = {
            "narrative_debt_threshold": 5,
            "arc_stagnation_days": 21,
            "strategy_moment_max_gap_days": 10,
        }
        config = _parse_strategy_config(data)
        assert config.narrative_debt_threshold == 5
        assert config.arc_stagnation_days == 21
        assert config.strategy_moment_max_gap_days == 10

    def test_parse_empty_dict_returns_defaults(self):
        """Empty dict returns default config values."""
        config = _parse_context_config({})
        assert config.recent_decisions == 30
        assert config.max_tokens == 150000

    def test_parse_partial_dict_fills_defaults(self):
        """Partial dict uses provided values, defaults for rest."""
        config = _parse_context_config({"recent_decisions": 10})
        assert config.recent_decisions == 10
        assert config.recent_posts == 15  # default

    def test_load_project_config_parses_typed_sections(self, temp_dir):
        """load_project_config parses context and strategy from content-config."""
        project_dir = temp_dir / "project"
        config_dir = project_dir / CONFIG_DIR_NAME
        config_dir.mkdir(parents=True)
        (config_dir / "content-config.yaml").write_text(
            """\
context:
  recent_decisions: 50
  max_tokens: 200000
strategy:
  narrative_debt_threshold: 5
"""
        )

        global_base = temp_dir / "global"
        global_base.mkdir()

        config = load_project_config(project_dir, global_base=global_base)
        assert config.context.recent_decisions == 50
        assert config.context.max_tokens == 200000
        assert config.context.recent_posts == 15  # default
        assert config.strategy.narrative_debt_threshold == 5
        assert config.strategy.arc_stagnation_days == 14  # default

    def test_load_project_config_no_yaml_uses_defaults(self, temp_dir):
        """No content-config.yaml still produces typed config with defaults."""
        project_dir = temp_dir / "project"
        project_dir.mkdir()
        global_base = temp_dir / "global"
        global_base.mkdir()

        config = load_project_config(project_dir, global_base=global_base)
        assert config.context.recent_decisions == 30
        assert config.context.max_tokens == 150000
        assert config.strategy.narrative_debt_threshold == 3


# =============================================================================
# MediaToolGuidance
# =============================================================================


class TestMediaToolGuidance:
    """Test MediaToolGuidance and _parse_media_guidance."""

    def test_defaults_have_four_tools(self):
        """DEFAULT_MEDIA_GUIDANCE has 4 structural tool slots (no opinionated content)."""
        assert len(DEFAULT_MEDIA_GUIDANCE) == 4
        assert "mermaid" in DEFAULT_MEDIA_GUIDANCE
        assert "nano_banana_pro" in DEFAULT_MEDIA_GUIDANCE
        assert "playwright" in DEFAULT_MEDIA_GUIDANCE
        assert "ray_so" in DEFAULT_MEDIA_GUIDANCE

        # Structural only — opinionated guidance lives in content-config.yaml
        mermaid = DEFAULT_MEDIA_GUIDANCE["mermaid"]
        assert mermaid.use_when == []
        assert mermaid.constraints == []
        assert mermaid.enabled is None
        assert mermaid.prompt_example is None

    def test_parse_empty_dict_returns_defaults(self):
        """Empty dict returns structural defaults (empty lists)."""
        result = _parse_media_guidance({})
        assert len(result) == 4
        assert result["mermaid"].use_when == []
        assert result["ray_so"].constraints == []

    def test_parse_preserves_unspecified_tools(self):
        """Override one tool, others keep structural defaults."""
        data = {
            "mermaid": {"enabled": False},
        }
        result = _parse_media_guidance(data)
        assert result["mermaid"].enabled is False
        # use_when/constraints remain empty (structural default)
        assert result["mermaid"].use_when == []
        assert result["mermaid"].constraints == []
        # Other tools unchanged
        assert result["nano_banana_pro"].enabled is None
        assert result["nano_banana_pro"].use_when == []

    def test_parse_overrides_specific_fields(self):
        """Override only specified fields, keep rest from structural default."""
        data = {
            "playwright": {
                "use_when": ["Custom use case"],
                "prompt_example": "screenshot of the dashboard",
            },
        }
        result = _parse_media_guidance(data)
        pw = result["playwright"]
        assert pw.use_when == ["Custom use case"]
        assert pw.prompt_example == "screenshot of the dashboard"
        # constraints remain empty (structural default)
        assert pw.constraints == []
        assert pw.enabled is None

    def test_parse_adds_custom_tool(self):
        """Custom tool not in defaults gets added."""
        data = {
            "custom_tool": {
                "enabled": True,
                "use_when": ["Special case"],
                "constraints": ["Be careful"],
            },
        }
        result = _parse_media_guidance(data)
        assert len(result) == 5
        assert result["custom_tool"].enabled is True
        assert result["custom_tool"].use_when == ["Special case"]

    def test_parse_does_not_mutate_defaults(self):
        """Parsing should not mutate DEFAULT_MEDIA_GUIDANCE."""
        original_mermaid_enabled = DEFAULT_MEDIA_GUIDANCE["mermaid"].enabled
        data = {"mermaid": {"enabled": True, "use_when": ["Overridden"]}}
        _parse_media_guidance(data)
        assert DEFAULT_MEDIA_GUIDANCE["mermaid"].enabled == original_mermaid_enabled
        assert DEFAULT_MEDIA_GUIDANCE["mermaid"].use_when == []

    def test_load_project_config_parses_media_guidance(self, temp_dir):
        """load_project_config parses media_tools from content-config."""
        project_dir = temp_dir / "project"
        config_dir = project_dir / CONFIG_DIR_NAME
        config_dir.mkdir(parents=True)
        (config_dir / "content-config.yaml").write_text(
            """\
media_tools:
  mermaid:
    enabled: false
  ray_so:
    prompt_example: "highlighted code snippet"
"""
        )

        global_base = temp_dir / "global"
        global_base.mkdir()

        config = load_project_config(project_dir, global_base=global_base)
        assert config.media_guidance["mermaid"].enabled is False
        assert config.media_guidance["ray_so"].prompt_example == "highlighted code snippet"
        # Unspecified tools have empty structural defaults
        assert config.media_guidance["nano_banana_pro"].use_when == []


# =============================================================================
# EpisodePreferences and StrategyConfig extensions
# =============================================================================


class TestStrategyConfigExtended:
    """Test StrategyConfig new fields: portfolio_window, episode_preferences."""

    def test_default_portfolio_window(self):
        """Default portfolio_window is 10."""
        config = StrategyConfig()
        assert config.portfolio_window == 10

    def test_default_episode_preferences(self):
        """Default episode_preferences has empty favor/avoid lists."""
        config = StrategyConfig()
        assert config.episode_preferences.favor == []
        assert config.episode_preferences.avoid == []

    def test_episode_preferences_dataclass(self):
        """EpisodePreferences stores favor/avoid lists."""
        ep = EpisodePreferences(favor=["milestone", "breakthrough"], avoid=["routine"])
        assert ep.favor == ["milestone", "breakthrough"]
        assert ep.avoid == ["routine"]

    def test_parse_strategy_with_new_fields(self):
        """Parse portfolio_window and episode_preferences from dict."""
        data = {
            "narrative_debt_threshold": 5,
            "portfolio_window": 20,
            "episode_preferences": {
                "favor": ["milestone", "breakthrough"],
                "avoid": ["routine"],
            },
        }
        config = _parse_strategy_config(data)
        assert config.portfolio_window == 20
        assert config.episode_preferences.favor == ["milestone", "breakthrough"]
        assert config.episode_preferences.avoid == ["routine"]
        assert config.narrative_debt_threshold == 5

    def test_parse_strategy_empty_keeps_defaults(self):
        """Empty dict keeps default portfolio_window and episode_preferences."""
        config = _parse_strategy_config({})
        assert config.portfolio_window == 10
        assert config.episode_preferences.favor == []
        assert config.episode_preferences.avoid == []

    def test_parse_strategy_partial_episode_preferences(self):
        """Partial episode_preferences only sets provided lists."""
        data = {
            "episode_preferences": {"favor": ["deep_dive"]},
        }
        config = _parse_strategy_config(data)
        assert config.episode_preferences.favor == ["deep_dive"]
        assert config.episode_preferences.avoid == []

    def test_load_project_config_parses_strategy_extensions(self, temp_dir):
        """load_project_config parses extended strategy fields."""
        project_dir = temp_dir / "project"
        config_dir = project_dir / CONFIG_DIR_NAME
        config_dir.mkdir(parents=True)
        (config_dir / "content-config.yaml").write_text(
            """\
strategy:
  portfolio_window: 15
  episode_preferences:
    favor:
      - milestone
    avoid:
      - routine
"""
        )

        global_base = temp_dir / "global"
        global_base.mkdir()

        config = load_project_config(project_dir, global_base=global_base)
        assert config.strategy.portfolio_window == 15
        assert config.strategy.episode_preferences.favor == ["milestone"]
        assert config.strategy.episode_preferences.avoid == ["routine"]


# =============================================================================
# SummaryConfig
# =============================================================================


class TestSummaryConfig:
    """Test SummaryConfig parsing."""

    def test_defaults(self):
        """Default SummaryConfig has refresh_after_commits=20, refresh_after_days=14."""
        config = SummaryConfig()
        assert config.refresh_after_commits == 20
        assert config.refresh_after_days == 14

    def test_parse_from_dict(self):
        """Parse SummaryConfig from dict."""
        data = {"refresh_after_commits": 50, "refresh_after_days": 30}
        config = _parse_summary_config(data)
        assert config.refresh_after_commits == 50
        assert config.refresh_after_days == 30

    def test_parse_empty_returns_defaults(self):
        """Empty dict returns default SummaryConfig."""
        config = _parse_summary_config({})
        assert config.refresh_after_commits == 20
        assert config.refresh_after_days == 14

    def test_parse_partial_fills_defaults(self):
        """Partial dict uses provided values, defaults for rest."""
        config = _parse_summary_config({"refresh_after_commits": 10})
        assert config.refresh_after_commits == 10
        assert config.refresh_after_days == 14  # default

    def test_load_project_config_parses_summary(self, temp_dir):
        """load_project_config parses summary from content-config."""
        project_dir = temp_dir / "project"
        config_dir = project_dir / CONFIG_DIR_NAME
        config_dir.mkdir(parents=True)
        (config_dir / "content-config.yaml").write_text(
            """\
summary:
  refresh_after_commits: 30
  refresh_after_days: 7
"""
        )

        global_base = temp_dir / "global"
        global_base.mkdir()

        config = load_project_config(project_dir, global_base=global_base)
        assert config.summary.refresh_after_commits == 30
        assert config.summary.refresh_after_days == 7

    def test_load_project_config_no_summary_uses_defaults(self, temp_dir):
        """No summary section uses defaults."""
        project_dir = temp_dir / "project"
        project_dir.mkdir()
        global_base = temp_dir / "global"
        global_base.mkdir()

        config = load_project_config(project_dir, global_base=global_base)
        assert config.summary.refresh_after_commits == 20
        assert config.summary.refresh_after_days == 14


# =============================================================================
# ConsolidationConfig
# =============================================================================


class TestConsolidationConfig:
    """Test ConsolidationConfig parsing and validation."""

    def test_default_config_has_consolidation_disabled(self):
        """Default config has consolidation disabled."""
        config = load_config(None)
        assert config.consolidation.enabled is False
        assert config.consolidation.mode == "notify_only"
        assert config.consolidation.batch_size == 20

    def test_parse_consolidation_config(self, temp_dir):
        """Parse consolidation from YAML."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
consolidation:
  enabled: true
  mode: re_evaluate
  batch_size: 50
"""
        )

        config = load_config(config_path)
        assert config.consolidation.enabled is True
        assert config.consolidation.mode == "re_evaluate"
        assert config.consolidation.batch_size == 50

    def test_invalid_consolidation_mode(self, temp_dir):
        """Invalid consolidation mode raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
consolidation:
  mode: invalid_mode
"""
        )

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "Invalid consolidation mode" in str(exc_info.value)

    def test_invalid_consolidation_batch_size(self, temp_dir):
        """Invalid batch_size raises ConfigError."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
consolidation:
  batch_size: 0
"""
        )

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "Invalid consolidation batch_size" in str(exc_info.value)

    def test_missing_consolidation_uses_defaults(self, temp_dir):
        """Config without consolidation section uses defaults."""
        config_path = temp_dir / "config.yaml"
        config_path.write_text(
            """\
models:
  evaluator: anthropic/claude-opus-4-5
"""
        )

        config = load_config(config_path)
        assert config.consolidation.enabled is False
        assert config.consolidation.mode == "notify_only"
        assert config.consolidation.batch_size == 20
