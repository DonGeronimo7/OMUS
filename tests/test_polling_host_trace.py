# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from mouse_control.hardware.base import HardwareError
from mouse_control.polling_host_trace_cli import _anchor_for_target, _positive_csv


def test_anchor_prefers_requested_anchor_when_different_from_target():
    rates = (1000, 500, 250, 125)
    assert _anchor_for_target(500, rates, 1000) == 1000
    assert _anchor_for_target(250, rates, 1000) == 1000


def test_anchor_uses_an_alternate_rate_when_target_is_preferred_anchor():
    rates = (1000, 500, 250, 125)
    assert _anchor_for_target(1000, rates, 1000) == 500


def test_anchor_requires_at_least_two_rates():
    with pytest.raises(HardwareError):
        _anchor_for_target(500, (500,), 1000)


def test_positive_csv_rejects_duplicates_and_nonpositive_values():
    with pytest.raises(Exception):
        _positive_csv('500,500')
    with pytest.raises(Exception):
        _positive_csv('500,0')
