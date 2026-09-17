from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected block not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


setup = Path("src/mouse_control/setup_tui.py")

replace_once(
    setup,
    '''        self.status = "Automatic Discovery complete. Review capabilities before configuration."\n''',
    '''        self.status = (\n            "Automatic Discovery complete. No verified host-accessible DPI/polling write path; "\n            "continue with DPI-stage observation and button remapping."\n            if self.no_write_path\n            else "Automatic Discovery complete. Review capabilities before configuration."\n        )\n''',
)

replace_once(
    setup,
    '''        else:\n            lines.append("? DPI capability not yet discovered")\n\n        if self.choices.polling_readable or self.choices.polling_writable:\n''',
    '''        else:\n            lines.append(\n                "— DPI write path unavailable; no verified host-accessible DPI protocol"\n                if self.discovery_complete\n                else "? DPI capability not yet discovered"\n            )\n\n        if self.choices.polling_readable or self.choices.polling_writable:\n''',
)

replace_once(
    setup,
    '''        else:\n            lines.append("? Polling capability not yet discovered")\n\n        if self._supports_dpi_events():\n            lines.append("✓ Physical DPI events")\n''',
    '''        else:\n            lines.append(\n                "— Polling write path unavailable; no verified host-accessible polling protocol"\n                if self.discovery_complete\n                else "? Polling capability not yet discovered"\n            )\n\n        if self.no_write_path:\n            lines.append("✓ Discovery complete: no verified host-accessible DPI/polling write path")\n            lines.append("✓ Button remapping remains available through evdev")\n\n        if self._supports_dpi_events():\n            lines.append("✓ Physical DPI events / stage notifications available")\n''',
)

replace_once(
    setup,
    '''    def row_count(self) -> int:\n''',
    '''    @property\n    def no_write_path(self) -> bool:\n        """True after discovery completes without DPI or polling write authority."""\n        return (\n            self.discovery_complete\n            and not self.choices.dpi_writable\n            and not self.choices.polling_writable\n        )\n\n    def _next_configuration_section(self, section: SetupSection | None = None) -> SetupSection:\n        """Skip configuration pages that cannot change the selected hardware."""\n        section = self.section if section is None else section\n        if section is SetupSection.HARDWARE:\n            if self.choices.dpi_writable:\n                return SetupSection.DPI\n            if self.choices.polling_writable:\n                return SetupSection.POLLING\n            return SetupSection.BUTTONS\n        if section is SetupSection.DPI:\n            return SetupSection.POLLING if self.choices.polling_writable else SetupSection.BUTTONS\n        if section is SetupSection.POLLING:\n            return SetupSection.BUTTONS\n        return SECTIONS[min(SECTIONS.index(section) + 1, len(SECTIONS) - 1)]\n\n    def _previous_configuration_section(self, section: SetupSection | None = None) -> SetupSection:\n        """Reverse navigation mirrors capability-driven forward navigation."""\n        section = self.section if section is None else section\n        if section is SetupSection.BUTTONS:\n            if self.choices.polling_writable:\n                return SetupSection.POLLING\n            if self.choices.dpi_writable:\n                return SetupSection.DPI\n            return SetupSection.HARDWARE\n        if section is SetupSection.POLLING:\n            return SetupSection.DPI if self.choices.dpi_writable else SetupSection.HARDWARE\n        if section is SetupSection.DPI:\n            return SetupSection.HARDWARE\n        return SECTIONS[max(SECTIONS.index(section) - 1, 0)]\n\n    def row_count(self) -> int:\n''',
)

replace_once(
    setup,
    '''        if key == "LEFT":\n            if self.nav.return_to is SetupSection.REVIEW and self.section in {\n                SetupSection.DPI, SetupSection.POLLING, SetupSection.BUTTONS\n            }:\n                self.nav.back()\n            else:\n                self.nav.sequential(-1)\n            self.row_cursor = self.device_cursor if self.section is SetupSection.DEVICE else 0\n            self._clamp_cursor()\n            return ControllerAction()\n        if key == "RIGHT":\n            self.nav.sequential(1)\n            self.row_cursor = self.device_cursor if self.section is SetupSection.DEVICE else 0\n            self._clamp_cursor()\n            return ControllerAction()\n''',
    '''        if key == "LEFT":\n            if self.nav.return_to is SetupSection.REVIEW and self.section in {\n                SetupSection.DPI, SetupSection.POLLING, SetupSection.BUTTONS\n            }:\n                self.nav.back()\n            elif self.section in {SetupSection.DPI, SetupSection.POLLING, SetupSection.BUTTONS}:\n                self._go(self._previous_configuration_section(), remember=False)\n            else:\n                self.nav.sequential(-1)\n            self.row_cursor = self.device_cursor if self.section is SetupSection.DEVICE else 0\n            self._clamp_cursor()\n            return ControllerAction()\n        if key == "RIGHT":\n            if self.nav.return_to is SetupSection.REVIEW and self.section in {\n                SetupSection.DPI, SetupSection.POLLING, SetupSection.BUTTONS\n            }:\n                self.nav.current = SetupSection.REVIEW\n                self.nav.return_to = None\n            elif self.section in {SetupSection.HARDWARE, SetupSection.DPI, SetupSection.POLLING}:\n                self._go(self._next_configuration_section())\n            else:\n                self.nav.sequential(1)\n            self.row_cursor = self.device_cursor if self.section is SetupSection.DEVICE else 0\n            self._clamp_cursor()\n            return ControllerAction()\n''',
)

replace_once(
    setup,
    '''                self._go(SetupSection.DPI)\n                return ControllerAction()\n            self._go(SetupSection.DPI)\n            return ControllerAction()\n''',
    '''                self._go(self._next_configuration_section(SetupSection.HARDWARE))\n                return ControllerAction()\n            self._go(self._next_configuration_section(SetupSection.HARDWARE))\n            return ControllerAction()\n''',
)

replace_once(
    setup,
    '''            if self.guided_discovery_available:\n                rows.append(DisplayRow("Continue deeper guided DPI learning", 1))\n                rows.append(DisplayRow("Continue to DPI configuration", 2))\n            else:\n                rows.append(DisplayRow("Continue to DPI configuration", 1))\n''',
    '''            next_section = self._next_configuration_section(SetupSection.HARDWARE)\n            next_label = f"Continue to {next_section.value.lower()} configuration"\n            if self.guided_discovery_available:\n                rows.append(DisplayRow("Continue deeper guided DPI learning", 1))\n                rows.append(DisplayRow(next_label, 2))\n            else:\n                rows.append(DisplayRow(next_label, 1))\n''',
)

architecture = Path("tests/test_setup_architecture.py")
text = architecture.read_text(encoding="utf-8")
append = r'''

class ObserveOnlyBackend(RangeBackend):
    def get_capabilities(self, _device):
        return HardwareCapabilities()

    def supports_dpi(self, _device): return False
    def get_dpi_values(self, _device): return []
    def supports_polling_rate(self, _device): return False
    def supports_polling_rate_writes(self, _device): return False
    def get_polling_rates(self, _device): return []
    def supports_dpi_events(self, _device): return True


def test_no_write_path_is_successful_discovery_and_skips_write_pages():
    backend = ObserveOnlyBackend()
    controller = SetupController(
        [MOUSE1],
        {},
        choices_factory=choices_factory,
        backend_factory=lambda _device: backend,
    )
    controller.discovery_complete = True

    assert controller.no_write_path is True
    lines = controller.hardware_lines()
    assert any("no verified host-accessible DPI/polling write path" in line for line in lines)
    assert any("Button remapping remains available" in line for line in lines)
    assert any("stage notifications available" in line for line in lines)

    controller.section_index = SECTIONS.index(SetupSection.HARDWARE)
    controller.row_cursor = controller.row_count() - 1
    controller.handle_key("ENTER")
    assert controller.section is SetupSection.BUTTONS
    controller.handle_key("LEFT")
    assert controller.section is SetupSection.HARDWARE


def test_capability_navigation_only_shows_writable_hardware_pages():
    controller, _ = make_controller()
    controller.choices.dpi_writable = False
    controller.choices.polling_writable = True
    controller.section_index = SECTIONS.index(SetupSection.HARDWARE)
    controller.handle_key("RIGHT")
    assert controller.section is SetupSection.POLLING

    controller.choices.dpi_writable = True
    controller.choices.polling_writable = False
    controller.section_index = SECTIONS.index(SetupSection.HARDWARE)
    controller.handle_key("RIGHT")
    assert controller.section is SetupSection.DPI
    controller.handle_key("RIGHT")
    assert controller.section is SetupSection.BUTTONS
'''
if "test_no_write_path_is_successful_discovery_and_skips_write_pages" not in text:
    architecture.write_text(text + append, encoding="utf-8")

setup_tests = Path("tests/test_setup_tui.py")
replace_once(
    setup_tests,
    '''    assert app.handle_key("ENTER").kind is ActionKind.NONE\n    assert app.section is SetupSection.DPI\n    assert "BTN_LEFT" in app.choices.mappings\n''',
    '''    assert app.handle_key("ENTER").kind is ActionKind.NONE\n    # No verified write path is a successful result; skip non-configurable pages.\n    assert app.section is SetupSection.BUTTONS\n    assert "BTN_LEFT" in app.choices.mappings\n''',
)

print("applied final no-write setup policy and regression coverage")
