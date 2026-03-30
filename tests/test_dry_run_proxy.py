"""Tests for social_hook.dry_run — generic DryRunProxy."""

import types

from social_hook.dry_run import DryRunProxy


def _make_target():
    """Create a fake module-like object with get/insert/update/delete functions."""
    mod = types.ModuleType("fake_ops")
    mod.get_item = lambda conn, item_id: {"id": item_id, "name": "test"}
    mod.insert_item = lambda conn, item: item.get("id") if isinstance(item, dict) else None
    mod.update_item = lambda conn, item_id, **kwargs: True
    mod.delete_item = lambda conn, item_id: True
    mod.increment_counter = lambda conn, name: 1
    mod.set_flag = lambda conn, name, value: True
    mod.reset_state = lambda conn: True
    mod.supersede_record = lambda conn, old_id, new_id: True
    return mod


class TestDryRunProxyPassthrough:
    """Tests that read operations pass through correctly."""

    def test_get_passes_through(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        result = proxy.get_item("item_1")
        assert result == {"id": "item_1", "name": "test"}

    def test_get_passes_through_even_when_dry_run(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        result = proxy.get_item("item_2")
        assert result["id"] == "item_2"

    def test_all_operations_pass_when_not_dry_run(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=False)
        assert proxy.delete_item("item_1") is True
        assert proxy.update_item("item_1", name="new") is True


class TestDryRunProxySkipping:
    """Tests that write operations are skipped in dry-run mode."""

    def test_insert_returns_id_from_dict(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        result = proxy.insert_item({"id": "new_1", "data": "x"})
        assert result == "new_1"

    def test_insert_returns_id_from_object(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)

        class FakeRecord:
            id = "rec_1"

        result = proxy.insert_item(FakeRecord())
        assert result == "rec_1"

    def test_insert_returns_none_without_id(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        result = proxy.insert_item("plain_string")
        assert result is None

    def test_update_returns_false(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        assert proxy.update_item("item_1", name="new") is False

    def test_delete_returns_none(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        assert proxy.delete_item("item_1") is None

    def test_increment_returns_zero(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        assert proxy.increment_counter("views") == 0

    def test_set_returns_false(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        assert proxy.set_flag("active", True) is False

    def test_reset_returns_false(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        assert proxy.reset_state() is False

    def test_supersede_returns_false(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=True)
        assert proxy.supersede_record("old", "new") is False


class TestDryRunProxyEdgeCases:
    """Edge cases and configuration."""

    def test_unknown_attribute_raises(self):
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=False)
        try:
            proxy.nonexistent_function()
            raise AssertionError("Should have raised")
        except AttributeError as e:
            assert "nonexistent_function" in str(e)

    def test_custom_read_prefixes(self):
        target = _make_target()
        # Treat "delete_" as a read operation (unusual but tests the parameter)
        proxy = DryRunProxy(
            target, first_arg="conn", dry_run=True, read_prefixes=("get_", "delete_")
        )
        assert proxy.delete_item("item_1") is True  # passes through
        assert proxy.update_item("item_1") is False  # skipped

    def test_no_first_arg(self):
        """Proxy without first_arg doesn't prepend anything."""
        mod = types.ModuleType("bare")
        mod.get_value = lambda key: f"val_{key}"
        proxy = DryRunProxy(mod, dry_run=False)
        assert proxy.get_value("x") == "val_x"

    def test_trigger_source_on_subclass(self):
        """DryRunContext-style subclass can set extra attributes."""
        target = _make_target()
        proxy = DryRunProxy(target, first_arg="conn", dry_run=False)
        proxy.trigger_source = "auto"
        assert proxy.trigger_source == "auto"
