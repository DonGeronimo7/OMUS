# SPDX-License-Identifier: AGPL-3.0-or-later
from scripts.check_license_consistency import check


def test_current_license_metadata_and_first_party_headers_are_consistent():
    assert check() == []
