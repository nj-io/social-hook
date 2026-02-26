"""Tests for social_hook.constants module."""

import ast
import importlib
from pathlib import Path

from social_hook.constants import (
    CONFIG_DIR_NAME,
    DB_FILENAME,
    MODULE_NAME,
    PROJECT_NAME,
    PROJECT_SLUG,
)


def test_slug_is_lowercase_hyphenated():
    assert PROJECT_SLUG == PROJECT_SLUG.lower()
    assert " " not in PROJECT_SLUG


def test_config_dir_starts_with_dot():
    assert CONFIG_DIR_NAME.startswith(".")


def test_db_filename_ends_with_db():
    assert DB_FILENAME.endswith(".db")


def test_module_name_uses_underscores():
    assert "-" not in MODULE_NAME
    assert " " not in MODULE_NAME


def test_no_internal_imports():
    """constants.py must have zero internal dependencies."""
    source_path = Path(importlib.util.find_spec("social_hook.constants").origin)
    tree = ast.parse(source_path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("social_hook"), (
                    f"constants.py must not import from social_hook: {node.module}"
                )
