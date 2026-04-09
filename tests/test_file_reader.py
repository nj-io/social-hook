"""Tests for file_reader.py — token-budgeted file loading."""

from social_hook.file_reader import read_files_within_budget


class TestReadFilesWithinBudget:
    def test_reads_files_within_budget(self, tmp_path):
        (tmp_path / "a.md").write_text("Hello world")
        (tmp_path / "b.md").write_text("Goodbye world")

        text, tokens = read_files_within_budget(
            ["a.md", "b.md"],
            tmp_path,
            max_tokens=10_000,
        )
        assert "Hello world" in text
        assert "Goodbye world" in text
        assert tokens > 0

    def test_budget_truncates_large_file(self, tmp_path):
        content = "x" * 4000  # ~1000 tokens
        (tmp_path / "big.md").write_text(content)

        text, tokens = read_files_within_budget(
            ["big.md"],
            tmp_path,
            max_tokens=100,
        )
        # Should be truncated
        assert "[...truncated]" in text
        assert tokens <= 100

    def test_skips_missing_files(self, tmp_path):
        (tmp_path / "exists.md").write_text("I exist")

        text, tokens = read_files_within_budget(
            ["exists.md", "missing.md"],
            tmp_path,
            max_tokens=10_000,
        )
        assert "I exist" in text
        assert "missing" not in text

    def test_path_traversal_protection(self, tmp_path):
        # Create a file outside base_dir
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / "secret.md").write_text("secret data")

        inner = tmp_path / "inner"
        inner.mkdir()
        (inner / "safe.md").write_text("safe data")

        text, tokens = read_files_within_budget(
            ["safe.md", "../outer/secret.md"],
            inner,
            max_tokens=10_000,
        )
        assert "safe data" in text
        assert "secret data" not in text

    def test_deduplication(self, tmp_path):
        (tmp_path / "doc.md").write_text("Unique content")

        text, tokens = read_files_within_budget(
            ["doc.md", "doc.md", "./doc.md"],
            tmp_path,
            max_tokens=10_000,
        )
        assert text.count("Unique content") == 1

    def test_skips_non_text_extensions(self, tmp_path):
        (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02")
        (tmp_path / "readme.md").write_text("Read me")

        text, tokens = read_files_within_budget(
            ["data.bin", "readme.md"],
            tmp_path,
            max_tokens=10_000,
        )
        assert "Read me" in text
        assert "\x00" not in text

    def test_custom_count_fn(self, tmp_path):
        (tmp_path / "doc.md").write_text("Hello")

        # Custom counter: 1 token per character
        text, tokens = read_files_within_budget(
            ["doc.md"],
            tmp_path,
            max_tokens=10_000,
            count_fn=len,
        )
        assert tokens == 5  # "Hello" is 5 characters

    def test_empty_paths_returns_empty(self, tmp_path):
        text, tokens = read_files_within_budget([], tmp_path, max_tokens=10_000)
        assert text == ""
        assert tokens == 0

    def test_budget_stops_at_limit(self, tmp_path):
        # Create two files, each ~250 tokens (1000 chars)
        (tmp_path / "a.md").write_text("a" * 1000)
        (tmp_path / "b.md").write_text("b" * 1000)

        text, tokens = read_files_within_budget(
            ["a.md", "b.md"],
            tmp_path,
            max_tokens=300,
        )
        # First file ~250 tokens, second would exceed budget
        assert "a" * 100 in text
        # Second file either truncated or excluded
        assert tokens <= 300

    def test_encoding_errors_handled(self, tmp_path):
        # Write binary content to a .md file
        (tmp_path / "broken.md").write_bytes(b"\x80\x81\x82 hello")
        (tmp_path / "good.md").write_text("Good content")

        text, tokens = read_files_within_budget(
            ["broken.md", "good.md"],
            tmp_path,
            max_tokens=10_000,
        )
        # errors="replace" should handle the bad encoding
        assert "Good content" in text

    def test_absolute_paths_within_base_work(self, tmp_path):
        (tmp_path / "doc.md").write_text("Absolute path test")

        text, tokens = read_files_within_budget(
            [str(tmp_path / "doc.md")],
            tmp_path,
            max_tokens=10_000,
        )
        assert "Absolute path test" in text
