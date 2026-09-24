# SPDX-License-Identifier: AGPL-3.0-or-later
from mouse_control.knowledge_provenance import KnowledgeClaim, operation_conflicts


def test_conflict_blocks_only_affected_operation_and_context() -> None:
    claims = (
        KnowledgeClaim("a", "project-a", "rev1", "dpi.write", "25a7:fa07", conflicts_with=("b",)),
        KnowledgeClaim("c", "project-a", "rev1", "battery.read", "25a7:fa07"),
    )
    assert [item.claim_id for item in operation_conflicts(claims, "dpi.write", "25a7:fa07")] == ["a"]
    assert operation_conflicts(claims, "battery.read", "25a7:fa07") == ()
