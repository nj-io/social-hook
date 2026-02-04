"""Tests for configuration functionality (T2, T9)."""

import pytest

from social_hook.config import load_config, load_env, load_full_config, load_project_config
from social_hook.config.project import save_memory
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

    def test_missing_required_key(self, temp_dir):
        """Missing required key raises ConfigError."""
        env_path = temp_dir / ".env"
        env_path.write_text("TELEGRAM_BOT_TOKEN=123456:ABC\n")

        with pytest.raises(ConfigError) as exc_info:
            load_env(env_path)

        assert "Missing required: ANTHROPIC_API_KEY" in str(exc_info.value)

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

        assert config.models.evaluator == "claude-opus-4-5"
        assert config.models.drafter == "claude-sonnet-4-5"
        assert config.models.gatekeeper == "claude-haiku-4-5"
        assert config.platforms.x.enabled is True
        assert config.platforms.x.account_tier == "free"
        assert config.scheduling.timezone == "America/Los_Angeles"

    def test_invalid_model_value(self, temp_dir):
        """Invalid model value raises ConfigError."""
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

    def test_missing_config_returns_default(self):
        """Missing config.yaml returns default Config."""
        config = load_config(None)

        assert config.models.evaluator == "claude-opus-4-5"
        assert config.models.drafter == "claude-opus-4-5"
        assert config.models.gatekeeper == "claude-haiku-4-5"

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
  evaluator: claude-sonnet-4-5
"""
        )

        config = load_full_config(env_path, yaml_path)

        assert config.env["ANTHROPIC_API_KEY"] == "sk-ant-test"
        assert config.models.evaluator == "claude-sonnet-4-5"


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

        config = load_project_config(empty_project)

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
