from pathlib import Path
import re
import tomllib

from mouse_control import __version__


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _project():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def test_release_versions_are_synchronized():
    version = __version__
    assert _project()["version"] == version
    assert f"Version:        {version}" in _text("mouse-control.spec")
    assert f"pkgver={version}" in _text("PKGBUILD")
    if (ROOT / ".SRCINFO").exists():
        assert f"pkgver = {version}" in _text(".SRCINFO")
        assert f"#tag=v{version}" in _text(".SRCINFO")
    assert _text("debian/changelog").startswith(f"mouse-control ({version}-1)")
    assert f"Version: {version}-1" in _text("packaging/debian-binary-control")
    assert f"The current release is [v{version}]" in _text("README.md")
    assert f"mouse-control-{version}-1.fc44.noarch.rpm" in _text("README.md")
    assert f"mouse-control_{version}-1_all.deb" in _text("README.md")
    assert f"Mouse-Control-{version}-x86_64.AppImage" in _text("README.md")
    assert f"Mouse-Control-{version}-x86_64.AppImage" in _text(
        "packaging/appimage/README.md"
    )
    assert _text("RELEASE_NOTES.md").startswith(f"# Mouse Control v{version}")
    assert f"## {version} — " in _text("CHANGELOG.md").splitlines()[2]


def test_rpm_packages_every_declared_console_script():
    scripts = set(_project()["scripts"])
    spec = _text("mouse-control.spec")
    files_section = spec.split("%files -f %{pyproject_files}", 1)[1].split(
        "%changelog", 1
    )[0]
    packaged = set(re.findall(r"%\{_bindir\}/([A-Za-z0-9._-]+)", files_section))
    assert packaged == scripts


def test_ci_and_release_workflow_are_version_independent():
    ci_path = ROOT / ".github/workflows/ci.yml"
    release_path = ROOT / ".github/workflows/release-artifacts.yml"
    if not ci_path.exists() or not release_path.exists():
        return

    version = __version__
    ci = ci_path.read_text(encoding="utf-8")
    release = release_path.read_text(encoding="utf-8")
    assert f"mouse-control-{version}" not in ci
    assert f"mouse-control-{version}" not in release
    assert "pyproject.toml" in ci
    assert "pyproject.toml" in release
    assert "permissions:\n  contents: read" in release
    assert "needs: [test, python, deb, rpm, appimage]" in release
    assert "permissions:\n      contents: write" in release
    assert 'test "$GITHUB_REF_NAME" = "v${version}"' in release
