import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


verify = _load("verify_virustotal_results", "scripts/verify_virustotal_results.py")
notes = _load("update_virustotal_release_notes", "scripts/update_virustotal_release_notes.py")


def test_workflow_verifies_sbom_checksum_but_excludes_it_from_scanning():
    workflow = (ROOT / ".github/workflows/virustotal-release.yml").read_text(
        encoding="utf-8"
    )
    assert '--pattern "omus-${version}.cdx.json"' in workflow
    assert "! -name '*.cdx.json'" in workflow
    assert "!scan-assets/*.cdx.json" in workflow
    assert "!scan-assets/SHA256SUMS" in workflow


def test_result_markdown_is_truthful_and_includes_preserved_evidence():
    rendered = verify.render_markdown([{
        "name": "mouse_control-0.9.9.tar.gz",
        "sha256": "a" * 64,
        "link": "https://www.virustotal.com/gui/file-analysis/example",
        "malicious": 0,
        "suspicious": 0,
        "undetected": 70,
    }])
    assert "0 detections at scan time" in rendered
    assert "not a certification of safety" in rendered
    assert "guaranteed virus free" not in rendered.lower()
    assert "a" * 64 in rendered


def test_result_markdown_reports_malicious_and_suspicious_counts():
    rendered = verify.render_markdown([{
        "name": "artifact.rpm", "sha256": "b" * 64, "link": "https://example.invalid",
        "malicious": 2, "suspicious": 3, "undetected": 65,
    }])
    assert "2 malicious, 3 suspicious" in rendered
    assert "0 detections" not in rendered


def test_release_note_update_is_idempotent():
    first = notes.update("release body", verify.render_markdown([]))
    second = notes.update(first, verify.render_markdown([]))
    assert first == second
    assert second.count(notes.START) == second.count(notes.END) == 1
