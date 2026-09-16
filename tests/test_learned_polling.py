from __future__ import annotations

from pathlib import Path

import pytest

from mouse_control.learned_operations import (
    LearnedOperationState,
    StableDeviceIdentity,
    StableInterfaceIdentity,
)
from mouse_control.learned_polling import (
    LearnedPollingOperationError,
    LearnedPollingOperationStore,
    PollingControlState,
    infer_learned_polling_operation,
    polling_operation_to_profile,
    promote_polling_operation,
    validate_learned_polling_profile,
)


RATES = (1000, 500, 250, 125)
RAW = {1000: 1, 500: 2, 250: 4, 125: 8}


def event(direction, data):
    return {
        "direction": direction,
        "data_hex": bytes(data).hex(),
        "relative_us": 0.0,
    }


def _base_profile(kind: str, demonstrations):
    return {
        "schema_version": 1,
        "profile_kind": kind,
        "write_authorized": False,
        "identity": {
            "bus": 3,
            "vendor_id": 0x046D,
            "product_id": 0x4074,
        },
        "fingerprints": {
            "model": "modelhash",
            "instance": "instancehash",
        },
        "interface": {
            "bus": 3,
            "vendor_id": 0x046D,
            "product_id": 0xC53F,
            "interface_number": 2,
            "descriptor_sha256": "descriptorhash",
        },
        "demonstrations": demonstrations,
    }


def onboard_profile():
    demonstrations = []
    for rate in RATES:
        raw = RAW[rate]
        demonstrations.append(
            {
                "target_hz": rate,
                "events": [
                    event("tx", b"\x10\x01"),
                    event("rx", b"\x20\x01\x01"),  # query => Onboard raw 1
                    event("tx", b"\x10\x02\x02"),
                    event("rx", b"\x20\x02\x00"),
                    event("tx", b"\x10\x01"),
                    event("rx", b"\x20\x01\x02"),  # verify => Host raw 2
                    event("tx", bytes((0x10, 0x04, raw))),
                    event("rx", b"\x20\x04\x00"),
                    event("tx", b"\x10\x05"),
                    event("rx", bytes((0x20, 0x05, raw))),
                ],
            }
        )
    return _base_profile("polling-demonstrations", demonstrations)


def host_profile():
    demonstrations = []
    for rate in RATES:
        raw = RAW[rate]
        demonstrations.append(
            {
                "target_hz": rate,
                "events": [
                    event("tx", b"\x10\x01"),
                    event("rx", b"\x20\x01\x02"),  # query => Host raw 2
                    event("tx", bytes((0x10, 0x04, raw))),
                    event("rx", b"\x20\x04\x00"),
                    event("tx", b"\x10\x05"),
                    event("rx", bytes((0x20, 0x05, raw))),
                ],
            }
        )
    return _base_profile("polling-host-demonstrations", demonstrations)


def _operation():
    return infer_learned_polling_operation(
        onboard_profile(),
        host_profile(),
        identity=StableDeviceIdentity(
            3,
            0x046D,
            0x4074,
            "modelhash",
            "instancehash",
        ),
        interface=StableInterfaceIdentity(
            3,
            0x046D,
            0xC53F,
            2,
            "descriptorhash",
        ),
    )


def _evidence():
    order = (500, 250, 125, 1000)
    return [
        {
            "target_hz": rate,
            "branch": (
                PollingControlState.ONBOARD.value
                if index == 0
                else PollingControlState.HOST.value
            ),
            "generic_readback_hz": rate,
            "physical_consensus_hz": rate,
            "confidence": "high" if rate != 250 else "medium",
            "accepted_passes": 3 if rate != 250 else 2,
            "total_passes": 3,
            "median_inferred_hz": float(rate),
            "median_error_fraction": 0.0,
        }
        for index, rate in enumerate(order)
    ]


def _rollback():
    return {
        "success": True,
        "original_rate_hz": 1000,
        "restored_rate_hz": 1000,
        "original_control_raw": 1,
        "restored_control_raw": 1,
    }


def _state():
    return {
        "persistent_generic_session": True,
        "native_reopened_between_generic_writes": False,
        "first_branch": "onboard",
        "subsequent_branch": "host",
    }


def test_infers_two_branch_state_machine_without_authority():
    operation = _operation()

    assert operation.state is LearnedOperationState.DEMONSTRATED
    assert operation.write_authorized is False
    assert operation.demonstrated_rates == (125, 250, 500, 1000)
    assert dict(operation.raw_to_hz) == {1: 1000, 2: 500, 4: 250, 8: 125}
    assert operation.control_state_offset == 2
    assert operation.onboard_state_raw == 1
    assert operation.host_state_raw == 2

    onboard = operation.replay_grammar(PollingControlState.ONBOARD)
    host = operation.replay_grammar(PollingControlState.HOST)
    assert len(onboard.steps) == 5
    assert len(host.steps) == 3
    assert onboard.steps[0].response.bytes_ == (0x20, 0x01, 0x01)
    assert host.steps[0].response.bytes_ == (0x20, 0x01, 0x02)
    assert onboard.raw_for_rate(500) == 2
    assert host.raw_for_rate(250) == 4


def test_promotion_requires_every_demonstrated_rate_and_verified_rollback():
    operation = _operation()

    with pytest.raises(LearnedPollingOperationError):
        promote_polling_operation(
            operation,
            rate_evidence=_evidence()[:-1],
            rollback_evidence=_rollback(),
            state_evidence=_state(),
        )

    bad_rollback = _rollback()
    bad_rollback["restored_control_raw"] = 2
    with pytest.raises(LearnedPollingOperationError):
        promote_polling_operation(
            operation,
            rate_evidence=_evidence(),
            rollback_evidence=bad_rollback,
            state_evidence=_state(),
        )

    promoted = promote_polling_operation(
        operation,
        rate_evidence=_evidence(),
        rollback_evidence=_rollback(),
        state_evidence=_state(),
    )
    assert promoted.state is LearnedOperationState.PROVEN
    assert promoted.write_authorized is True
    assert promoted.promotion_evidence["persistent_session"] is True


def test_proven_state_cannot_be_forged_without_physical_evidence():
    profile = polling_operation_to_profile(_operation())
    profile["status"] = "proven"
    profile["write_authorized"] = True

    with pytest.raises(LearnedPollingOperationError):
        validate_learned_polling_profile(profile)


def test_proven_profile_round_trips_and_store_does_not_confuse_dpi_profiles(tmp_path: Path):
    promoted = promote_polling_operation(
        _operation(),
        rate_evidence=_evidence(),
        rollback_evidence=_rollback(),
        state_evidence=_state(),
    )
    store = LearnedPollingOperationStore(tmp_path)
    path = store.save(promoted)

    # An unrelated JSON profile in the same learned-operations directory must be
    # ignored instead of breaking enumeration.
    (tmp_path / "unrelated.json").write_text(
        '{"schema_version":1,"profile_kind":"learned-operation"}\n',
        encoding="utf-8",
    )

    loaded = store.load(path)
    assert loaded.state is LearnedOperationState.PROVEN
    assert loaded.write_authorized
    assert loaded.replay_grammar(PollingControlState.ONBOARD).raw_for_rate(125) == 8
    assert len(store.operations()) == 1


def test_inference_rejects_corpora_that_do_not_share_one_control_query():
    host = host_profile()
    for demonstration in host["demonstrations"]:
        demonstration["events"][0]["data_hex"] = b"\x10\x99".hex()

    with pytest.raises(LearnedPollingOperationError):
        infer_learned_polling_operation(
            onboard_profile(),
            host,
            identity=StableDeviceIdentity(
                3, 0x046D, 0x4074, "modelhash", "instancehash"
            ),
            interface=StableInterfaceIdentity(
                3, 0x046D, 0xC53F, 2, "descriptorhash"
            ),
        )
