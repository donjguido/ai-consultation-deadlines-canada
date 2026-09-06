"""Status rules. These encode the model the funder-facing plan describes:
four statuses (new, open, closing soon, retired), a 14-day "new" window and a
7-day "closing soon" window. Changing pipeline/models.py should fail these loudly."""
from datetime import timedelta

import pytest

from pipeline import models
from tests.conftest import TODAY, make_item


def test_windows_are_the_documented_values():
    assert models.NEW_WINDOW_DAYS == 14
    assert models.CLOSING_SOON_DAYS == 7


def test_only_four_badge_values_exist(sample_items):
    seen = set()
    for item in sample_items:
        seen.update(item.badges(TODAY))
        assert item.status(TODAY) in {"open", "retired"}
    assert seen == {"new", "open", "closing_soon", "retired"}


def test_new_window_boundaries():
    assert make_item(opened=TODAY - timedelta(days=14)).is_new(TODAY)
    assert not make_item(opened=TODAY - timedelta(days=15)).is_new(TODAY)


def test_new_falls_back_to_first_seen_when_opened_missing():
    assert make_item(opened=None, first_seen=TODAY - timedelta(days=1)).is_new(TODAY)
    assert not make_item(opened=None, first_seen=TODAY - timedelta(days=30)).is_new(TODAY)


def test_closing_soon_boundaries():
    assert make_item(closes=TODAY).is_closing_soon(TODAY)
    assert make_item(closes=TODAY + timedelta(days=7)).is_closing_soon(TODAY)
    assert not make_item(closes=TODAY + timedelta(days=8)).is_closing_soon(TODAY)
    assert not make_item(closes=None).is_closing_soon(TODAY)


def test_expired_and_flagged_items_are_retired_and_nothing_else():
    expired = make_item(closes=TODAY - timedelta(days=1))
    flagged = make_item(retired=True, retired_reason="closed", closes=TODAY + timedelta(days=2))
    for item in (expired, flagged):
        assert item.status(TODAY) == "retired"
        assert item.badges(TODAY) == ["retired"]
        assert not item.is_new(TODAY)
        assert not item.is_closing_soon(TODAY)


def test_badges_order_and_open_always_last():
    both = make_item(opened=TODAY - timedelta(days=1), closes=TODAY + timedelta(days=1))
    assert both.badges(TODAY) == ["new", "closing_soon", "open"]
    assert make_item(opened=TODAY - timedelta(days=60)).badges(TODAY) == ["open"]


def test_verified_defaults_false():
    assert make_item().verified is False
    assert "verified" in models.Item.model_fields


def test_relevance_is_bounded():
    with pytest.raises(Exception):
        make_item(relevance=1.5)
