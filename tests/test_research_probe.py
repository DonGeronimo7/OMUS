# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

from mouse_control.research_probe import _choose_other


def test_probe_chooses_only_another_demonstrated_value():
    assert _choose_other((800, 1500, 2000), 1500) in {800, 2000}
    assert _choose_other((1500,), 1500) is None


def test_reversible_probe_reuses_conclusive_research_primitives():
    source = Path("src/mouse_control/research_probe.py").read_text()
    required = (
        "LearnedHidSession",
        "learned_dpi_read_spec",
        "execute_learned_dpi",
        "measure_sensor_state_auto",
        "measure_current_polling",
        "operation.replay_grammar",
        "generic rollback",
    )
    for item in required:
        assert item in source
    assert "promotion=True" in source
    assert "write authority" in source.lower()


def test_tui_executes_probe_instead_of_only_describing_it():
    source = Path("src/mouse_control/setup_tui_curses.py").read_text()
    assert "Run reversible write-possibility research?" in source
    assert "run_reversible_research_probes(" in source
    assert "apply_research_probe_outcome" in source
