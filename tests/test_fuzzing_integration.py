from pathlib import Path
import ast
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_workflows import validate_repository


def test_clusterfuzzlite_configuration_is_pinned_and_policy_compliant():
    assert validate_repository() == []
    dockerfile = (ROOT / ".clusterfuzzlite/Dockerfile").read_text(encoding="utf-8")
    assert "base-builder-python@sha256:" in dockerfile
    assert ":latest" not in dockerfile


def test_clusterfuzzlite_build_does_not_weaken_python_or_dependency_policy():
    build = (ROOT / ".clusterfuzzlite/build.sh").read_text(encoding="utf-8")
    assert "pyinstaller --paths src" in build
    assert "pip install" not in build


def test_fuzz_targets_are_pure_and_have_bounded_inputs():
    prohibited_modules = {"dbus_next", "socket", "subprocess", "urllib"}
    prohibited_calls = {"open", "connect", "send", "write", "request"}
    paths = sorted((ROOT / "fuzz").glob("*_fuzzer.py"))
    assert {path.name for path in paths} == {
        "hid_descriptor_fuzzer.py",
        "vendor_capture_fuzzer.py",
    }
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "MAX_INPUT_BYTES" in source
        tree = ast.parse(source, filename=str(path))
        imports = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            (node.module or "").split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        } | {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert imports.isdisjoint(prohibited_modules)
        assert calls.isdisjoint(prohibited_calls)


def test_fuzz_seed_corpora_and_local_smoke_command_are_present():
    assert list((ROOT / "fuzz/corpus/hid_descriptor_fuzzer").iterdir())
    assert list((ROOT / "fuzz/corpus/vendor_capture_fuzzer").iterdir())
    smoke = (ROOT / "scripts/run-fuzz-smoke.sh").read_text(encoding="utf-8")
    assert "-runs=100" in smoke
    assert "hid_descriptor_fuzzer.py" in smoke
    assert "vendor_capture_fuzzer.py" in smoke
