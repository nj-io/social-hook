"""Tests for social_hook.registry — generic AdapterRegistry."""

import pytest

from social_hook.registry import AdapterRegistry


class TestAdapterRegistry:
    """Core registry operations."""

    def test_register_and_create(self):
        reg = AdapterRegistry("test")
        reg.register("foo", lambda: "foo_instance")
        assert reg.create("foo") == "foo_instance"

    def test_create_unknown_raises_key_error(self):
        reg = AdapterRegistry("test")
        with pytest.raises(KeyError, match="Unknown test adapter: 'bar'"):
            reg.create("bar")

    def test_create_unknown_lists_available(self):
        reg = AdapterRegistry("test")
        reg.register("alpha", lambda: None)
        reg.register("beta", lambda: None)
        with pytest.raises(KeyError, match="alpha, beta"):
            reg.create("gamma")

    def test_create_passes_args_and_kwargs(self):
        def factory(x, y, *, z=0):
            return x + y + z

        reg = AdapterRegistry("test")
        reg.register("add", factory)
        assert reg.create("add", 1, 2, z=3) == 6

    def test_has(self):
        reg = AdapterRegistry("test")
        assert not reg.has("foo")
        reg.register("foo", lambda: None)
        assert reg.has("foo")

    def test_contains(self):
        reg = AdapterRegistry("test")
        reg.register("foo", lambda: None)
        assert "foo" in reg
        assert "bar" not in reg

    def test_names(self):
        reg = AdapterRegistry("test")
        reg.register("b", lambda: None)
        reg.register("a", lambda: None)
        # Preserves insertion order
        assert reg.names() == ["b", "a"]

    def test_len(self):
        reg = AdapterRegistry("test")
        assert len(reg) == 0
        reg.register("x", lambda: None)
        assert len(reg) == 1

    def test_repr(self):
        reg = AdapterRegistry("platform")
        reg.register("x", lambda: None)
        reg.register("linkedin", lambda: None)
        assert repr(reg) == "AdapterRegistry('platform', [linkedin, x])"


class TestMetadata:
    """Metadata registration and retrieval."""

    def test_register_with_metadata(self):
        reg = AdapterRegistry("test")
        reg.register("foo", lambda: None, metadata={"display_name": "Foo Tool"})
        assert reg.get_metadata("foo") == {"display_name": "Foo Tool"}

    def test_get_metadata_unknown_returns_empty(self):
        reg = AdapterRegistry("test")
        assert reg.get_metadata("missing") == {}

    def test_get_metadata_no_metadata_returns_empty(self):
        reg = AdapterRegistry("test")
        reg.register("foo", lambda: None)
        assert reg.get_metadata("foo") == {}

    def test_get_metadata_returns_copy(self):
        reg = AdapterRegistry("test")
        reg.register("foo", lambda: None, metadata={"key": "val"})
        meta = reg.get_metadata("foo")
        meta["key"] = "mutated"
        assert reg.get_metadata("foo")["key"] == "val"

    def test_all_metadata(self):
        reg = AdapterRegistry("test")
        reg.register("a", lambda: None, metadata={"name": "A"})
        reg.register("b", lambda: None)
        result = reg.all_metadata()
        assert result == {"a": {"name": "A"}, "b": {}}


class TestCaching:
    """get_or_create caching behavior."""

    def test_get_or_create_caches(self):
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return f"instance_{call_count}"

        reg = AdapterRegistry("test")
        reg.register("foo", factory)

        first = reg.get_or_create("foo")
        second = reg.get_or_create("foo")

        assert first == "instance_1"
        assert second == "instance_1"
        assert first is second
        assert call_count == 1

    def test_invalidate_clears_single(self):
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return f"instance_{call_count}"

        reg = AdapterRegistry("test")
        reg.register("foo", factory)
        reg.register("bar", factory)

        reg.get_or_create("foo")
        reg.get_or_create("bar")
        assert call_count == 2

        reg.invalidate("foo")
        reg.get_or_create("foo")
        assert call_count == 3

        # bar still cached
        reg.get_or_create("bar")
        assert call_count == 3

    def test_clear_cache(self):
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return call_count

        reg = AdapterRegistry("test")
        reg.register("foo", factory)
        reg.get_or_create("foo")
        assert call_count == 1

        reg.clear_cache()
        reg.get_or_create("foo")
        assert call_count == 2

    def test_create_always_fresh(self):
        """create() never uses cache, unlike get_or_create()."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return call_count

        reg = AdapterRegistry("test")
        reg.register("foo", factory)

        assert reg.create("foo") == 1
        assert reg.create("foo") == 2
        assert call_count == 2

    def test_invalidate_nonexistent_is_noop(self):
        reg = AdapterRegistry("test")
        reg.invalidate("does_not_exist")  # Should not raise
