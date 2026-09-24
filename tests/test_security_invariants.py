# SPDX-License-Identifier: AGPL-3.0-or-later
"""Static tripwires for reviewed security boundaries."""

from pathlib import Path
import ast
import re


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "mouse_control"


def test_production_python_uses_no_shell_eval_exec_or_pickle():
    violations = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant)
                       and keyword.value.value is True for keyword in node.keywords):
                    violations.append(f"{path}: shell=True")
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                    violations.append(f"{path}: {node.func.id}")
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    if (node.func.value.id, node.func.attr) == ("os", "system"):
                        violations.append(f"{path}: os.system")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""])
                if any(name == "pickle" or name.startswith("pickle.") for name in names):
                    violations.append(f"{path}: pickle import")
    assert violations == []


def test_network_client_is_confined_to_explicit_updater_and_netlink_cannot_send():
    network_modules = {"urllib", "requests", "socket", "http", "httpx", "aiohttp"}
    consumers = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.ImportFrom):
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in network_modules:
                        consumers.add(path.name)
            if module and module.split(".", 1)[0] in network_modules:
                consumers.add(path.name)
    assert consumers == {"runtime_wake.py", "updater.py"}

    wake_path = SRC / "runtime_wake.py"
    wake_tree = ast.parse(wake_path.read_text(encoding="utf-8"), filename=str(wake_path))
    socket_calls = {
        node.func.attr
        for node in ast.walk(wake_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "AF_NETLINK" in wake_path.read_text(encoding="utf-8")
    assert socket_calls.isdisjoint({"connect", "connect_ex", "send", "sendall", "sendto"})


def test_workflow_actions_are_full_sha_pinned_and_token_scope_is_narrow():
    workflow_dir = ROOT / ".github" / "workflows"
    if not workflow_dir.exists():
        return
    workflows = list(workflow_dir.glob("*.yml"))
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        for reference in re.findall(r"uses:\s*([^\s#]+)", text):
            assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", reference), (workflow, reference)
    release = (ROOT / ".github/workflows/release-artifacts.yml").read_text(encoding="utf-8")
    assert "permissions: read-all" in release
    assert "if: github.ref_type == 'tag'" in release
    assert "sha256sum * > SHA256SUMS" in release


def test_appimage_downloads_are_verified_before_extract_or_execute():
    build = (ROOT / "packaging/appimage/build-appimage.sh").read_text(encoding="utf-8")
    assert "PY_RUNTIME_SHA256=" in build
    assert build.index("sha256sum --check --strict") < build.index("tar -xzf")
    assert "AppDir/usr/python/bin/$script" in build
    assert "-name '*.pyc'" in build and "-name '*.pyo'" in build
    assert "-name __pycache__ -empty -delete" in build
    release_path = ROOT / ".github/workflows/release-artifacts.yml"
    if not release_path.exists():
        return
    release = release_path.read_text(encoding="utf-8")
    assert release.index("sha256sum --check --strict") < release.index("chmod +x /tmp/appimagetool.AppImage")


def test_udev_rules_exclude_keyboard_and_blanket_world_access():
    rules = (ROOT / "src/mouse_control/udev/71-mouse-control-uaccess.rules").read_text(encoding="utf-8")
    assert 'ENV{ID_INPUT_KEYBOARD}!="1"' in rules
    assert "MODE=\"0666\"" not in rules
    assert 'SUBSYSTEM=="hidraw"' in rules and "046D:4074" in rules
