"""Tests for ``social_hook.media_tokens`` — article inline-positioning parser."""

from social_hook.media_tokens import MediaToken, extract_tokens, resolve_tokens


class TestExtractTokens:
    def test_empty_content_returns_empty(self):
        assert extract_tokens("") == []
        assert extract_tokens("no tokens here") == []

    def test_single_token(self):
        tokens = extract_tokens("lead ![cap](media:media_abc123) tail")
        assert len(tokens) == 1
        assert tokens[0].caption == "cap"
        assert tokens[0].media_id == "media_abc123"

    def test_preserves_source_order(self):
        content = "one ![a](media:id1) two ![b](media:id2) three"
        tokens = extract_tokens(content)
        assert [t.media_id for t in tokens] == ["id1", "id2"]
        assert tokens[0].start < tokens[1].start

    def test_empty_caption_allowed(self):
        tokens = extract_tokens("![](media:id_only)")
        assert len(tokens) == 1
        assert tokens[0].caption == ""
        assert tokens[0].media_id == "id_only"

    def test_malformed_tokens_ignored(self):
        # missing closing paren
        assert extract_tokens("![cap](media:no_paren") == []
        # wrong scheme
        assert extract_tokens("![cap](http://example.com/a.png)") == []
        # missing colon
        assert extract_tokens("![cap](media-abc)") == []

    def test_start_end_offsets_are_usable(self):
        content = "XX ![c](media:mx) YY"
        tokens = extract_tokens(content)
        t = tokens[0]
        assert content[t.start : t.end] == "![c](media:mx)"

    def test_caption_allows_spaces(self):
        tokens = extract_tokens("![hello world](media:mx)")
        assert tokens[0].caption == "hello world"

    def test_permissive_id_charset(self):
        # The id regex admits a-zA-Z0-9_- so malformed-but-recognizable
        # ids still extract; the diagnostics catch mismatches at read time.
        tokens = extract_tokens("![c](media:NotValidFormatButMatches_123-x)")
        assert len(tokens) == 1
        assert tokens[0].media_id == "NotValidFormatButMatches_123-x"


class TestResolveTokens:
    def test_empty_content_passthrough(self):
        assert resolve_tokens("", {}) == ""

    def test_orphan_token_survives(self):
        out = resolve_tokens("see ![x](media:missing_xyz)", {})
        assert out == "see ![x](media:missing_xyz)"

    def test_resolved_token_replaced(self):
        out = resolve_tokens("see ![x](media:abc)", {"abc": "/p/a.png"})
        assert out == "see ![x](/p/a.png)"

    def test_partial_resolution(self):
        # Some resolved, some orphan — orphans survive.
        out = resolve_tokens(
            "a ![c1](media:id1) b ![c2](media:id2) c",
            {"id1": "/path/1.png"},
        )
        assert out == "a ![c1](/path/1.png) b ![c2](media:id2) c"

    def test_empty_path_treated_as_orphan(self):
        # An empty path is indistinguishable from missing in the mapping.
        out = resolve_tokens("![](media:abc)", {"abc": ""})
        assert out == "![](media:abc)"

    def test_caption_preserved_on_resolve(self):
        out = resolve_tokens("![hello world](media:abc)", {"abc": "/p.png"})
        assert out == "![hello world](/p.png)"


class TestMediaTokenDataclass:
    def test_frozen(self):
        import pytest

        t = MediaToken(caption="c", media_id="mid", start=0, end=10)
        with pytest.raises(AttributeError):
            t.caption = "changed"
