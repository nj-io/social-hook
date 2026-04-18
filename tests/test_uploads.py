"""Tests for ``social_hook.uploads`` — shared upload validation helper."""

from __future__ import annotations

import pytest

from social_hook.errors import ConfigError
from social_hook.uploads import (
    ALLOWED_FORMATS,
    MAX_BYTES,
    parse_violation,
    validate_upload,
)


class TestConstants:
    def test_max_bytes_reads_single_image_max_size(self):
        """MAX_BYTES must pull 5 MiB from adapters.models.SINGLE_IMAGE.max_size."""
        from social_hook.adapters.models import SINGLE_IMAGE

        assert SINGLE_IMAGE.max_size == MAX_BYTES
        assert MAX_BYTES == 5 * 1024 * 1024

    def test_allowed_formats_is_union_of_single_image_and_gif(self):
        from social_hook.adapters.models import GIF, SINGLE_IMAGE

        expected = set(SINGLE_IMAGE.formats) | set(GIF.formats)
        assert expected == ALLOWED_FORMATS
        # png + jpg + webp + gif at minimum.
        assert {"png", "jpg", "webp", "gif"}.issubset(ALLOWED_FORMATS)


class TestValidateUploadHappyPath:
    @pytest.mark.parametrize("ext", sorted(ALLOWED_FORMATS))
    def test_accepts_each_allowed_format_with_small_file(self, ext):
        validate_upload(data=b"x", filename=f"photo.{ext}")

    def test_jpeg_is_normalized_to_jpg(self):
        """jpeg and jpg are treated as equivalent (only jpg in SINGLE_IMAGE.formats)."""
        validate_upload(data=b"x", filename="photo.JPEG")
        validate_upload(size_bytes=100, filename="photo.jpeg")

    def test_accepts_size_at_limit(self):
        validate_upload(size_bytes=MAX_BYTES, filename="max.png")

    def test_size_bytes_path_no_data_required(self):
        """CLI passes size_bytes; no need to load bytes into memory."""
        validate_upload(size_bytes=1024, filename="cli.png")


class TestValidateUploadFormatReject:
    def test_rejects_svg(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_upload(data=b"x", filename="logo.svg")
        assert str(exc_info.value).startswith("unsupported_format")

    def test_rejects_bmp(self):
        """BMP is not in SINGLE_IMAGE.formats + GIF.formats."""
        with pytest.raises(ConfigError) as exc_info:
            validate_upload(data=b"x", filename="img.bmp")
        assert str(exc_info.value).startswith("unsupported_format")

    def test_rejects_missing_extension(self):
        with pytest.raises(ConfigError):
            validate_upload(data=b"x", filename="no_ext")

    def test_rejects_no_filename(self):
        with pytest.raises(ConfigError):
            validate_upload(data=b"x", filename=None)

    def test_case_insensitive_extension(self):
        validate_upload(data=b"x", filename="A.PNG")
        with pytest.raises(ConfigError):
            validate_upload(data=b"x", filename="A.SVG")


class TestValidateUploadSizeReject:
    def test_rejects_over_limit_by_one_byte(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_upload(data=b"x" * (MAX_BYTES + 1), filename="too_big.png")
        msg = str(exc_info.value)
        assert msg.startswith("file_too_large")
        assert str(MAX_BYTES) in msg

    def test_rejects_when_size_unknown(self):
        """No data AND no size_bytes → refuse (don't silently pass)."""
        with pytest.raises(ConfigError) as exc_info:
            validate_upload(filename="mystery.png")
        assert "file_too_large" in str(exc_info.value)


class TestParseViolation:
    def test_parses_file_too_large(self):
        kind, detail = parse_violation("file_too_large: 999 > 5242880")
        assert kind == "file_too_large"
        assert detail == "999 > 5242880"

    def test_parses_unsupported_format(self):
        kind, detail = parse_violation("unsupported_format: .svg not in ['gif', 'jpg']")
        assert kind == "unsupported_format"
        assert detail.startswith(".svg")

    def test_unknown_kind_for_arbitrary_message(self):
        kind, detail = parse_violation("something_else: detail")
        assert kind == "unknown"
        assert detail == "something_else: detail"
