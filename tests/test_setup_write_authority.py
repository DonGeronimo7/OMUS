# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path


def test_tui_setup_final_apply_is_capability_gated():
    source = Path("src/mouse_control/setup_entry.py").read_text()
    assert "choices.dpi_writable and apply_dpi" in source
    assert "choices.polling_writable and apply_polling" in source
    assert "dpi_request" in source
    assert "polling_request" in source


def test_deeper_learning_is_research_plan_driven_not_generic_nonwritable():
    source = Path("src/mouse_control/setup_tui.py").read_text()
    section = source[source.index("def guided_discovery_available"):]
    section = section[:section.index("def _discovered_capability")]
    assert "deeper_learning_recommended" in section
    assert "not self.choices.dpi_writable" not in section
