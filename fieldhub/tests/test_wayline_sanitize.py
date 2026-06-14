"""wayline name sanitization - dji-forbidden chars must never reach the route list."""

import pytest

from app.services.wayline_library import sanitize_wayline_name


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("RWY22 PAPI inspection", "RWY22 PAPI inspection"),  # already clean, unchanged
        ("RWY22_PAPI/insp:01", "RWY22 PAPI insp 01"),  # forbidden -> space, collapsed
        ('a<b>c"d|e?f*g\\h.i', "a b c d e f g h i"),  # every forbidden char
        ("  spaced   out  ", "spaced out"),  # whitespace collapses and trims
        ("___", "wayline"),  # all-forbidden falls back, never blank
        ("", "wayline"),  # empty falls back
    ],
)
def test_sanitize_wayline_name(raw, expected):
    """forbidden chars collapse to single spaces, an empty result falls back."""
    assert sanitize_wayline_name(raw) == expected
