"""Tests for configuration functionality (T2, T9, T20d)."""

import pytest

from social_hook.config import load_config, load_env, load_full_config, load_project_config
from social_hook.config.project import (
    ContextConfig,
    StrategyConfig,
    _parse_context_config,
    _parse_strategy_config,
    save_memory,
)
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
        config_dir = project_dir / ".social-hook"
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

        config_dir = project_dir / ".social-hook"
        assert not config_dir.exists(), "Directory should not exist yet"

        save_memory(project_dir, "test context", "test feedback", "draft-001")

        assert config_dir.exists(), "save_memory should create .social-hook directory"
        assert (config_dir / "memories.md").exists(), "memories.md should be created"

    def test_save_memory_appends_entry(self, temp_project_dir):
        """save_memory appends new entry to existing memories.md."""
        config = load_project_config(temp_project_dir)
        original_memories = config.memories

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
        project_config_dir = project_dir / ".social-hook"
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
        project_config_dir = project_dir / ".social-hook"
        project_config_dir.mkdir(parents=True)
        (project_config_dir / "content-config.yaml").write_text("platforms:\n  x:\n    enabled: true")

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
        config_dir = project_dir / ".social-hook"
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
