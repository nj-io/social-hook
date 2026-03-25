"""MkDocs hooks for dynamic site configuration."""

from pathlib import Path

import tomllib


def on_config(config):
    """Inject project version from pyproject.toml into MkDocs config."""
    pyproject = Path(config["config_file_path"]).parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        version = tomllib.load(f)["project"]["version"]
    config["extra"]["version"] = version
    return config
