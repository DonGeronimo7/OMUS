from __future__ import annotations

from pathlib import Path
import tomllib
from unittest.mock import patch

from mouse_control import app, cli
from mouse_control.identity import canonical_directory


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_and_legacy_commands_share_one_dispatcher():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["omus"] == "mouse_control.app:main"
    assert scripts["mouse-control"] == scripts["omus"]
    with patch.object(cli, "main", return_value=23) as dispatcher:
        assert app.main(["status"]) == 23
    dispatcher.assert_called_once_with(["status"])


def test_cli_and_desktop_present_omus():
    assert cli._build_parser().prog == "omus"
    desktop = (ROOT / "packaging/appimage/omus.desktop").read_text()
    assert "Name=OMUS\n" in desktop
    assert "Exec=omus-launcher\n" in desktop
    assert "Icon=omus\n" in desktop


def test_legacy_config_tree_is_copied_once_and_retained(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    legacy = tmp_path / "mouse-control"
    legacy.mkdir()
    (legacy / "config.toml").write_text("[dpi]\nactive = 1500\n")
    (legacy / "evidence.json").write_text('{"proven": true}')

    canonical = canonical_directory("config")
    assert (canonical / "config.toml").read_text() == "[dpi]\nactive = 1500\n"
    assert (canonical / "evidence.json").read_text() == '{"proven": true}'
    assert (legacy / "config.toml").is_file()

    (legacy / "config.toml").write_text("legacy changed")
    assert canonical_directory("config") == canonical
    assert (canonical / "config.toml").read_text() == "[dpi]\nactive = 1500\n"


def test_existing_canonical_state_wins_over_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    (tmp_path / "mouse-control").mkdir()
    (tmp_path / "mouse-control" / "state").write_text("legacy")
    (tmp_path / "omus").mkdir()
    (tmp_path / "omus" / "state").write_text("canonical")
    assert (canonical_directory("data") / "state").read_text() == "canonical"


def test_current_facing_metadata_has_no_legacy_brand():
    current = [
        ROOT / "packaging/appimage/omus.desktop",
        ROOT / "packaging/omus.metainfo.xml",
    ]
    for path in current:
        assert "Mouse Control" not in path.read_text()
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src" / "mouse_control").rglob("*.py")
        if "Mouse Control" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_updater_accepts_canonical_and_v099_artifact_names(monkeypatch):
    from mouse_control import updater

    monkeypatch.setattr(updater, "_architecture", lambda: "x86_64")
    for name in (
        "omus-1.0.0-1.fc44.noarch.rpm",
        "omus_1.0.0_all.deb",
        "OMUS-1.0.0-x86_64.AppImage",
    ):
        suffix = ".appimage" if name.endswith("AppImage") else Path(name).suffix
        release = updater.Release("1.0.0", ({
            "name": name,
            "browser_download_url": f"https://github.com/DonGeronimo7/OMUS/releases/download/v1.0.0/{name}",
        },))
        assert updater.select_asset(release, suffix)["name"] == name


def test_current_repository_identity_is_canonical():
    from mouse_control import updater

    assert updater.REPOSITORY == "DonGeronimo7/OMUS"
    assert updater.RELEASE_URL == (
        "https://api.github.com/repos/DonGeronimo7/OMUS/releases/latest"
    )
    canonical_files = (
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "PKGBUILD",
        "pyproject.toml",
        "omus.spec",
        "packaging/omus.metainfo.xml",
        "docs/SECURITY_SUPPLY_CHAIN.md",
    )
    for relative in canonical_files:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "DonGeronimo7/mouse-control" not in text, relative
        assert "DonGeronimo7/OMUS" in text, relative


def test_release_workflows_use_canonical_artifact_names():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    virustotal = (
        ROOT / ".github/workflows/virustotal-release.yml"
    ).read_text(encoding="utf-8")
    assert "rpmbuild -ba omus.spec" in ci
    assert "name 'omus-*.noarch.rpm'" in ci
    for name in (
        "omus-${base_version}-${package_release}.fc44.noarch.rpm",
        "omus_${version}_all.deb",
        "OMUS-${version}-x86_64.AppImage",
        "omus-${python_version}-py3-none-any.whl",
        "omus-${python_version}.tar.gz",
        "omus-${version}.cdx.json",
    ):
        assert name in virustotal
    assert '"mouse-control-${base_version}' not in virustotal
    assert '"mouse_control-${python_version}' not in virustotal
