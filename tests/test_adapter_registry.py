"""Tests for AdapterRegistry (process-scoped adapter cache)."""

from unittest.mock import MagicMock, patch

from social_hook.adapters.platform.registry import AdapterRegistry
from social_hook.config.targets import AccountConfig, PlatformCredentialConfig


class TestAdapterRegistry:
    def test_get_creates_adapter(self):
        registry = AdapterRegistry()
        mock_adapter = MagicMock()

        with patch(
            "social_hook.adapters.platform.registry.create_adapter",
            return_value=mock_adapter,
        ) as mock_create:
            config = MagicMock()
            result = registry.get("x", config, db_path="/tmp/test.db")

            assert result is mock_adapter
            mock_create.assert_called_once_with("x", config, db_path="/tmp/test.db")

    def test_get_returns_cached(self):
        registry = AdapterRegistry()
        mock_adapter = MagicMock()

        with patch(
            "social_hook.adapters.platform.registry.create_adapter",
            return_value=mock_adapter,
        ) as mock_create:
            config = MagicMock()
            first = registry.get("x", config, db_path="/tmp/test.db")
            second = registry.get("x", config, db_path="/tmp/test.db")

            assert first is second
            assert mock_create.call_count == 1  # Only created once

    def test_different_keys_different_adapters(self):
        registry = AdapterRegistry()
        mock_x = MagicMock(name="x_adapter")
        mock_li = MagicMock(name="li_adapter")

        with patch(
            "social_hook.adapters.platform.registry.create_adapter",
            side_effect=[mock_x, mock_li],
        ):
            config = MagicMock()
            x = registry.get("x", config)
            li = registry.get("linkedin", config)

            assert x is mock_x
            assert li is mock_li
            assert x is not li

    def test_invalidate(self):
        registry = AdapterRegistry()
        mock_old = MagicMock(name="old")
        mock_new = MagicMock(name="new")

        with patch(
            "social_hook.adapters.platform.registry.create_adapter",
            side_effect=[mock_old, mock_new],
        ):
            config = MagicMock()
            first = registry.get("x", config)
            assert first is mock_old

            registry.invalidate("x")
            second = registry.get("x", config)
            assert second is mock_new
            assert second is not first

    def test_invalidate_nonexistent_key(self):
        registry = AdapterRegistry()
        # Should not raise
        registry.invalidate("nonexistent")

    def test_clear(self):
        registry = AdapterRegistry()
        mock_adapter = MagicMock()

        with patch(
            "social_hook.adapters.platform.registry.create_adapter",
            return_value=mock_adapter,
        ) as mock_create:
            config = MagicMock()
            registry.get("x", config)
            registry.get("linkedin", config)

            registry.clear()

            # Both should be recreated
            registry.get("x", config)
            registry.get("linkedin", config)
            assert mock_create.call_count == 4


class TestAdapterRegistryForAccount:
    """Tests for get_for_account() — targets-style per-account caching."""

    def _make_account(self, platform="x", tier="free"):
        return AccountConfig(platform=platform, tier=tier)

    def _make_creds(self, platform="x"):
        return PlatformCredentialConfig(platform=platform, client_id="cid", client_secret="csec")

    def test_get_for_account_creates_adapter(self):
        registry = AdapterRegistry()
        mock_adapter = MagicMock()
        account = self._make_account()
        creds = self._make_creds()

        with patch(
            "social_hook.adapters.platform.factory.create_adapter_from_account",
            return_value=mock_adapter,
        ) as mock_create:
            result = registry.get_for_account("my-x", account, creds, {}, "/tmp/test.db")

            assert result is mock_adapter
            mock_create.assert_called_once_with(
                "my-x", account, creds, {}, "/tmp/test.db", on_error=None
            )

    def test_get_for_account_returns_cached(self):
        registry = AdapterRegistry()
        mock_adapter = MagicMock()
        account = self._make_account()
        creds = self._make_creds()

        with patch(
            "social_hook.adapters.platform.factory.create_adapter_from_account",
            return_value=mock_adapter,
        ) as mock_create:
            first = registry.get_for_account("my-x", account, creds, {}, "/tmp/test.db")
            second = registry.get_for_account("my-x", account, creds, {}, "/tmp/test.db")

            assert first is second
            assert mock_create.call_count == 1

    def test_different_account_names_different_instances(self):
        """Two X accounts get separate adapter instances."""
        registry = AdapterRegistry()
        mock_x1 = MagicMock(name="x_personal")
        mock_x2 = MagicMock(name="x_business")
        account = self._make_account()
        creds = self._make_creds()

        with patch(
            "social_hook.adapters.platform.factory.create_adapter_from_account",
            side_effect=[mock_x1, mock_x2],
        ):
            first = registry.get_for_account("x-personal", account, creds, {}, "/tmp/test.db")
            second = registry.get_for_account("x-business", account, creds, {}, "/tmp/test.db")

            assert first is mock_x1
            assert second is mock_x2
            assert first is not second

    def test_invalidate_account(self):
        registry = AdapterRegistry()
        mock_old = MagicMock(name="old")
        mock_new = MagicMock(name="new")
        account = self._make_account()
        creds = self._make_creds()

        with patch(
            "social_hook.adapters.platform.factory.create_adapter_from_account",
            side_effect=[mock_old, mock_new],
        ):
            first = registry.get_for_account("my-x", account, creds, {}, "/tmp/test.db")
            assert first is mock_old

            registry.invalidate("my-x")
            second = registry.get_for_account("my-x", account, creds, {}, "/tmp/test.db")
            assert second is mock_new

    def test_on_error_passed_through(self):
        registry = AdapterRegistry()
        mock_adapter = MagicMock()
        account = self._make_account()
        creds = self._make_creds()
        error_cb = MagicMock()

        with patch(
            "social_hook.adapters.platform.factory.create_adapter_from_account",
            return_value=mock_adapter,
        ) as mock_create:
            registry.get_for_account("my-x", account, creds, {}, "/tmp/test.db", on_error=error_cb)

            mock_create.assert_called_once_with(
                "my-x", account, creds, {}, "/tmp/test.db", on_error=error_cb
            )

    def test_legacy_get_and_account_share_cache(self):
        """Legacy get() and get_for_account() use the same dict."""
        registry = AdapterRegistry()
        mock_legacy = MagicMock(name="legacy")
        mock_account = MagicMock(name="account")
        account = self._make_account()
        creds = self._make_creds()

        with patch(
            "social_hook.adapters.platform.registry.create_adapter",
            return_value=mock_legacy,
        ):
            legacy = registry.get("x", MagicMock())

        with patch(
            "social_hook.adapters.platform.factory.create_adapter_from_account",
            return_value=mock_account,
        ):
            acct = registry.get_for_account("my-x-account", account, creds, {}, "/tmp/test.db")

        # Different keys, different instances
        assert legacy is not acct
        # Clear removes both
        registry.clear()
        assert registry._adapters == {}
