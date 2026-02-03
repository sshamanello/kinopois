"""Tests for utility functions."""

from kinopois.utils import safe_filename, parse_rating, get_primary_genre


def test_safe_filename():
    """Test safe filename generation."""
    assert safe_filename("Hello World") == "Hello_World"
    assert safe_filename("драма") == "драма"
    assert safe_filename("test@#$%file") == "test_file"
    assert safe_filename("") == "unnamed"


def test_parse_rating():
    """Test rating parsing."""
    assert parse_rating("7.5") == 7.5
    assert parse_rating("7,5") == 7.5
    assert parse_rating("") == 0.0
    assert parse_rating(None) == 0.0
    assert parse_rating("invalid") == 0.0


def test_get_primary_genre():
    """Test primary genre extraction."""
    assert get_primary_genre("драма, комедия") == "драма"
    assert get_primary_genre("триллер") == "триллер"
    assert get_primary_genre("") == ""
    assert get_primary_genre(None) == ""
