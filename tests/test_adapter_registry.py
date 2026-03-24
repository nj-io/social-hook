"""Tests for AdapterRegistry (process-scoped adapter cache)."""

from unittest.mock import MagicMock, patch

from social_hook.adapters.platform.registry import AdapterRegistry


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
