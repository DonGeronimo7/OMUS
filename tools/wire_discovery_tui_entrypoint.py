from pathlib import Path

cli_path = Path('src/mouse_control/cli.py')
text = cli_path.read_text()
old = 'def run_setup_wizard() -> int:\n'
if old not in text:
    raise SystemExit('legacy setup function not found')
text = text.replace(old, 'def _run_legacy_setup_wizard() -> int:\n', 1)
marker = '\ndef _apply_hardware(backend: HardwareBackend, device: MouseDevice,\n'
if marker not in text:
    raise SystemExit('hardware marker not found')
wrapper = '''\ndef run_setup_wizard() -> int:\n    \"\"\"Run the production discovery-first full-screen setup TUI.\"\"\"\n    from .setup_entry import run_tui_setup_wizard\n\n    return run_tui_setup_wizard()\n\n\n'''
text = text.replace(marker, wrapper + marker, 1)
cli_path.write_text(text)

test_path = Path('tests/test_setup_entrypoint.py')
test_path.write_text('''from mouse_control import cli\n\n\ndef test_cli_setup_routes_to_discovery_first_entrypoint(monkeypatch):\n    called = []\n\n    def fake_tui():\n        called.append(True)\n        return 37\n\n    import mouse_control.setup_entry as setup_entry\n    monkeypatch.setattr(setup_entry, \"run_tui_setup_wizard\", fake_tui)\n\n    assert cli.run_setup_wizard() == 37\n    assert called == [True]\n\n\ndef test_main_setup_uses_discovery_first_entrypoint(monkeypatch):\n    monkeypatch.setattr(cli, \"run_setup_wizard\", lambda: 23)\n    assert cli.main([\"setup\"]) == 23\n''')

print('wired production setup command to discovery-first TUI')
