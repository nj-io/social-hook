"""Tests for MermaidAdapter (T7).

Source: WS3_ADAPTERS.md T7 (lines 176-184)
Source: WS3_ASSUMPTIONS.md A7 (lines 270-313) - PAKO encoding
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from social_hook.adapters.media.mermaid import MermaidAdapter, encode_mermaid

# =============================================================================
# T7: MermaidAdapter - PAKO Encoding
# =============================================================================


class TestMermaidEncoding:
    """T7: PAKO compression encoding for mermaid.ink."""

    def test_encode_produces_pako_prefix(self):
        """Encoded string starts with 'pako:' prefix."""
        result = encode_mermaid("graph LR\n  A-->B")
        assert result.startswith("pako:")

    def test_encode_url_safe_base64(self):
        """Encoded string uses URL-safe base64 (no + or /)."""
        result = encode_mermaid("graph TD\n  A-->B\n  B-->C\n  C-->D")
        encoded_part = result[len("pako:") :]
        assert "+" not in encoded_part
        assert "/" not in encoded_part

    def test_encode_with_theme(self):
        """Encoding includes theme parameter."""
        result_default = encode_mermaid("graph LR\n  A-->B", theme="default")
        result_dark = encode_mermaid("graph LR\n  A-->B", theme="dark")
        # Different themes produce different encodings
        assert result_default != result_dark

    def test_encode_deterministic(self):
        """Same input produces same output."""
        result1 = encode_mermaid("graph LR\n  A-->B")
        result2 = encode_mermaid("graph LR\n  A-->B")
        assert result1 == result2


# =============================================================================
# T7: MermaidAdapter - Core
# =============================================================================


class TestMermaidAdapter:
    """T7: MermaidAdapter generation and supports()."""

    def test_supports_mermaid(self):
        """supports('mermaid') returns True."""
        adapter = MermaidAdapter()
        assert adapter.supports("mermaid") is True

    def test_supports_diagram(self):
        """supports('diagram') returns True."""
        adapter = MermaidAdapter()
        assert adapter.supports("diagram") is True

    def test_supports_flowchart(self):
        """supports('flowchart') returns True."""
        adapter = MermaidAdapter()
        assert adapter.supports("flowchart") is True

    def test_supports_unknown(self):
        """supports('unknown') returns False."""
        adapter = MermaidAdapter()
        assert adapter.supports("image") is False

    def test_missing_diagram_spec(self):
        """Missing 'diagram' or 'code' in spec returns error."""
        adapter = MermaidAdapter()
        result = adapter.generate({})
        assert result.success is False
        assert "Missing" in result.error

    def test_dry_run(self):
        """dry_run=True returns placeholder path without API call."""
        adapter = MermaidAdapter()
        with patch("social_hook.adapters.media.mermaid.requests.get") as mock_get:
            result = adapter.generate({"diagram": "graph LR\n  A-->B"}, dry_run=True)
            mock_get.assert_not_called()

        assert result.success is True
        assert result.file_path is not None

    @patch("social_hook.adapters.media.mermaid.shutil.which", return_value=None)
    @patch("social_hook.adapters.media.mermaid.requests.get")
    def test_generate_success(self, mock_get, mock_which, tmp_path):
        """Successful generation saves PNG and returns file_path."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # Fake PNG header
        mock_get.return_value = mock_resp

        adapter = MermaidAdapter()
        result = adapter.generate(
            {"diagram": "graph LR\n  A-->B"},
            output_dir=str(tmp_path),
        )

        assert result.success is True
        assert result.file_path is not None
        assert result.file_path.endswith(".png")

    @patch("social_hook.adapters.media.mermaid.shutil.which", return_value=None)
    @patch("social_hook.adapters.media.mermaid.requests.get")
    def test_generate_api_error(self, mock_get, mock_which):
        """API error returns MediaResult(success=False)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_get.return_value = mock_resp

        adapter = MermaidAdapter()
        result = adapter.generate({"diagram": "invalid%%syntax"})

        assert result.success is False
        assert result.error is not None

    @patch("social_hook.adapters.media.mermaid.shutil.which", return_value=None)
    @patch("social_hook.adapters.media.mermaid.requests.get")
    def test_generate_uses_pako_encoding_in_url(self, mock_get, mock_which):
        """Request URL contains pako: encoded diagram."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG" + b"\x00" * 50
        mock_get.return_value = mock_resp

        adapter = MermaidAdapter()
        adapter.generate({"diagram": "graph LR\n  A-->B"})

        url = mock_get.call_args.args[0]
        assert "mermaid.ink/img/pako:" in url


# =============================================================================
# T7: MermaidAdapter - mmdc CLI Fallback
# =============================================================================


class TestMermaidMmdcFallback:
    """T7: MermaidAdapter mmdc CLI fallback."""

    @patch("social_hook.adapters.media.mermaid.subprocess.run")
    @patch("social_hook.adapters.media.mermaid.shutil.which")
    def test_mmdc_available_and_succeeds(self, mock_which, mock_run, tmp_path):
        """When mmdc is installed and succeeds, uses local rendering."""
        mock_which.return_value = "/usr/local/bin/mmdc"

        # Make subprocess.run create the output file
        def fake_run(cmd, **kwargs):
            output_idx = cmd.index("-o") + 1
            output_path = cmd[output_idx]
            Path(output_path).write_bytes(b"\x89PNG" + b"\x00" * 50)
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = fake_run

        adapter = MermaidAdapter()
        result = adapter.generate(
            {"diagram": "graph LR\n  A-->B"},
            output_dir=str(tmp_path),
        )

        assert result.success is True
        assert result.file_path is not None
        assert result.file_path.endswith(".png")
        mock_run.assert_called_once()

    @patch("social_hook.adapters.media.mermaid.shutil.which", return_value=None)
    @patch("social_hook.adapters.media.mermaid.requests.get")
    def test_mmdc_not_available_falls_back_to_api(self, mock_get, mock_which, tmp_path):
        """When mmdc is not installed, falls back to mermaid.ink API."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG" + b"\x00" * 50
        mock_get.return_value = mock_resp

        adapter = MermaidAdapter()
        result = adapter.generate(
            {"diagram": "graph LR\n  A-->B"},
            output_dir=str(tmp_path),
        )

        assert result.success is True
        mock_get.assert_called_once()  # API was used

    @patch("social_hook.adapters.media.mermaid.subprocess.run")
    @patch("social_hook.adapters.media.mermaid.shutil.which")
    @patch("social_hook.adapters.media.mermaid.requests.get")
    def test_mmdc_failure_falls_back_to_api(self, mock_get, mock_which, mock_run, tmp_path):
        """When mmdc fails, falls back to mermaid.ink API."""
        mock_which.return_value = "/usr/local/bin/mmdc"
        mock_run.return_value = MagicMock(returncode=1, stderr="Parse error")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNG" + b"\x00" * 50
        mock_get.return_value = mock_resp

        adapter = MermaidAdapter()
        result = adapter.generate(
            {"diagram": "graph LR\n  A-->B"},
            output_dir=str(tmp_path),
        )

        assert result.success is True
        mock_get.assert_called_once()  # API was used as fallback

    @patch("social_hook.adapters.media.mermaid.subprocess.run")
    @patch("social_hook.adapters.media.mermaid.shutil.which")
    def test_mmdc_passes_theme(self, mock_which, mock_run, tmp_path):
        """mmdc receives -t flag for non-default themes."""
        mock_which.return_value = "/usr/local/bin/mmdc"

        def fake_run(cmd, **kwargs):
            output_idx = cmd.index("-o") + 1
            output_path = cmd[output_idx]
            Path(output_path).write_bytes(b"\x89PNG" + b"\x00" * 50)
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = fake_run

        adapter = MermaidAdapter()
        adapter.generate(
            {"diagram": "graph LR\n  A-->B", "theme": "dark"},
            output_dir=str(tmp_path),
        )

        cmd = mock_run.call_args.args[0]
        assert "-t" in cmd
        assert "dark" in cmd

    @patch("social_hook.adapters.media.mermaid.subprocess.run")
    @patch("social_hook.adapters.media.mermaid.shutil.which")
    def test_mmdc_cleans_up_input_file(self, mock_which, mock_run, tmp_path):
        """mmdc temp input file is cleaned up after execution."""
        mock_which.return_value = "/usr/local/bin/mmdc"

        def fake_run(cmd, **kwargs):
            output_idx = cmd.index("-o") + 1
            output_path = cmd[output_idx]
            Path(output_path).write_bytes(b"\x89PNG" + b"\x00" * 50)
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = fake_run

        adapter = MermaidAdapter()
        adapter.generate(
            {"diagram": "graph LR\n  A-->B"},
            output_dir=str(tmp_path),
        )

        # No .mmd input files should remain
        mmd_files = list(tmp_path.glob("*.mmd"))
        assert len(mmd_files) == 0
