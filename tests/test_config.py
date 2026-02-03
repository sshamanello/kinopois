"""Tests for configuration."""

from kinopois.config import config, Config


def test_config_defaults():
    """Test default configuration values."""
    assert config.collage_tile_width == 500
    assert config.collage_tile_height == 750
    assert config.csv_delimiter == ";"
    assert config.csv_encoding == "utf-8-sig"


def test_config_paths():
    """Test that paths are Path objects."""
    from pathlib import Path
    assert isinstance(config.data_dir, Path)
    assert isinstance(config.posters_dir, Path)
    assert isinstance(config.collages_dir, Path)
    assert isinstance(config.cache_dir, Path)
