from pathlib import Path


def replace(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f'expected block not found in {path}')
    p.write_text(text.replace(old, new, 1))


replace(
    'tests/test_setup_tui.py',
    '''def test_unknown_device_offers_guided_discovery_and_can_skip():\n    unknown = {\n        MOUSE1.path: FakeBackend(dpi=False, polling=False, protocol=None),\n        MOUSE2.path: FakeBackend(),\n    }\n    app, _ = controller(backends=unknown)\n    app.section_index = SECTIONS.index(SetupSection.HARDWARE)\n    assert app.guided_discovery_available is True\n    assert app.handle_key("ENTER").kind in {\n        ActionKind.AUTOMATIC_DISCOVERY, ActionKind.RETRY_DISCOVERY\n    }\n    app.row_cursor = 1\n    assert app.handle_key("ENTER").kind is ActionKind.GUIDED_DISCOVERY\n    app.row_cursor = 2\n    assert app.handle_key("ENTER").kind is ActionKind.NONE\n    # No verified write path is a successful result; skip non-configurable pages.\n    assert app.section is SetupSection.BUTTONS\n    assert "BTN_LEFT" in app.choices.mappings\n''',
    '''def test_unknown_device_offers_deeper_learning_only_after_automatic_research_plan():\n    unknown = {\n        MOUSE1.path: FakeBackend(dpi=False, polling=False, protocol=None),\n        MOUSE2.path: FakeBackend(),\n    }\n    app, _ = controller(backends=unknown)\n    app.section_index = SECTIONS.index(SetupSection.HARDWARE)\n    # Deeper learning is not a pre-discovery generic escape hatch.\n    assert app.guided_discovery_available is False\n    assert app.handle_key("ENTER").kind is ActionKind.AUTOMATIC_DISCOVERY\n\n    app.discovery_complete = True\n    app.research_plan = SimpleNamespace(deeper_learning_recommended=True)\n    assert app.guided_discovery_available is True\n    app.row_cursor = 1\n    assert app.handle_key("ENTER").kind is ActionKind.GUIDED_DISCOVERY\n    app.row_cursor = 2\n    assert app.handle_key("ENTER").kind is ActionKind.NONE\n    # No verified write path is a successful result; skip non-configurable pages.\n    assert app.section is SetupSection.BUTTONS\n    assert "BTN_LEFT" in app.choices.mappings\n''',
)

replace(
    'tests/test_setup_tui_entry.py',
    '''        dpi_changed=True,\n        polling_changed=True,\n    )\n''',
    '''        dpi_changed=True,\n        polling_changed=True,\n        dpi_writable=True,\n        polling_writable=True,\n    )\n''',
)
print('integration test contracts aligned')
