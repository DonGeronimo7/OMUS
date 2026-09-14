"""Safe, explicit update dispatch for Mouse Control installations.

This deliberately delegates to the mechanism which owns the running copy; it
never replaces files owned by a system package manager.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen
from packaging.version import InvalidVersion, Version

from . import __version__
from .service import is_service_active, restart_service

RELEASE_URL = "https://api.github.com/repos/DonGeronimo7/mouse-control/releases/latest"


class UpdateError(RuntimeError):
    """An update could not safely be completed."""


@dataclass(frozen=True)
class Release:
    version: str
    assets: tuple[dict, ...]


@dataclass(frozen=True)
class Installation:
    kind: str
    executable: Path
    package: str | None = None
    detail: str = ""

    @property
    def description(self) -> str:
        return {"rpm": "RPM package (DNF)", "deb": "DEB package (APT)",
                "arch": "pacman package", "appimage": "AppImage",
                "pip": "Python/pip installation", "source": "Source/development checkout",
                "unknown": "unknown installation"}[self.kind]


def is_newer(latest: str, installed: str) -> bool:
    """Compare release tags with PEP 440 parsing, never mixed Python types."""
    try:
        return Version(latest.strip().lstrip("vV")) > Version(installed.strip().lstrip("vV"))
    except InvalidVersion as exc:
        raise UpdateError(f"Unsupported release version: {exc}") from exc


def _run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, **kwargs)  # type: ignore[arg-type]


def running_executable(argv0: str | None = None) -> Path:
    """Resolve the entry point being invoked, rather than an unrelated PATH copy."""
    raw = argv0 if argv0 is not None else sys.argv[0]
    return Path(raw).expanduser().resolve()


def _owned_by(command: list[str]) -> str | None:
    if not shutil.which(command[0]):
        return None
    result = _run(command)
    return result.stdout.strip() if result.returncode == 0 else None


def _loaded_source_checkout() -> Path | None:
    """Return the checkout containing the code loaded in this process, if any.

    Metadata can describe a different copy visible to Python.  ``__file__`` is
    the authoritative provenance signal here because it identifies the module
    that is currently executing.
    """
    package_dir = Path(__file__).resolve().parent
    source_dir = package_dir.parent
    checkout = source_dir.parent
    if package_dir.name == "mouse_control" and source_dir.name == "src" and (checkout / ".git").exists():
        return checkout
    return None


def detect_installation(executable: Path | None = None) -> Installation:
    executable = executable or running_executable()
    checkout = _loaded_source_checkout()
    if checkout is not None:
        return Installation("source", executable, detail=f"running from {checkout}")
    rpm = _owned_by(["rpm", "-qf", "--qf", "%{NAME}\\n", str(executable)])
    if rpm:
        return Installation("rpm", executable, rpm.splitlines()[0])
    deb = _owned_by(["dpkg-query", "-S", str(executable)])
    if deb:
        return Installation("deb", executable, deb.split(":", 1)[0])
    arch = _owned_by(["pacman", "-Qo", str(executable)])
    if arch:
        package = arch.partition(" is owned by ")[2].split(" ", 1)[0] or None
        return Installation("arch", executable, package)
    appimage = os.environ.get("APPIMAGE")
    if appimage or executable.suffix.lower() == ".appimage":
        return Installation("appimage", Path(appimage or executable).resolve())
    try:
        dist = importlib.metadata.distribution("mouse-control")
        direct = dist.read_text("direct_url.json")
        if direct and json.loads(direct).get("dir_info", {}).get("editable"):
            return Installation("source", executable, detail="editable pip install")
        return Installation("pip", executable, "mouse-control")
    except importlib.metadata.PackageNotFoundError:
        return Installation("unknown", executable)
    except (json.JSONDecodeError, OSError):
        return Installation("source", executable, detail="unverifiable Python source install")


def fetch_latest(url: str = RELEASE_URL, opener: Callable = urlopen) -> Release:
    try:
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "mouse-control-updater"})
        with opener(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub release information could not be retrieved.") from exc
    if not isinstance(data, dict) or data.get("prerelease") or data.get("draft"):
        raise UpdateError("GitHub did not return a stable release.")
    tag = data.get("tag_name")
    assets = data.get("assets")
    if not isinstance(tag, str) or not isinstance(assets, list):
        raise UpdateError("GitHub returned malformed release information.")
    return Release(tag.lstrip("vV"), tuple(asset for asset in assets if isinstance(asset, dict)))


def _architecture() -> str:
    return _normalize_architecture(platform.machine())


def _normalize_architecture(value: str) -> str:
    machine = value.lower()
    return {"amd64": "x86_64", "x86-64": "x86_64", "x64": "x86_64",
            "arm64": "aarch64"}.get(machine, machine)


def _safe_asset_filename(asset_name: str) -> str:
    """Reject release metadata that could select a local destination path."""
    if (not asset_name or asset_name in {".", ".."} or "/" in asset_name
            or "\\" in asset_name or Path(asset_name).is_absolute()
            or Path(asset_name).name != asset_name):
        raise UpdateError("Release asset has an unsafe filename.")
    return asset_name


def _asset_matches(name: str, version: str, suffix: str, architecture: str) -> bool:
    """Match only documented Mouse Control release filenames."""
    escaped_version = re.escape(version.lstrip("vV"))
    if suffix == ".rpm":
        match = re.fullmatch(rf"mouse-control-{escaped_version}-.+\.([^.]+)\.rpm", name)
        return bool(match and (match.group(1) == "noarch"
                               or _normalize_architecture(match.group(1)) == architecture))
    if suffix == ".deb":
        match = re.fullmatch(rf"mouse-control_{escaped_version}_([^_]+)\.deb", name)
        return bool(match and (match.group(1) == "all"
                               or _normalize_architecture(match.group(1)) == architecture))
    if suffix == ".appimage":
        match = re.fullmatch(rf"Mouse-Control-{escaped_version}-(.+)\.AppImage", name)
        return bool(match and _normalize_architecture(match.group(1)) == architecture)
    return False


def select_asset(release: Release, suffix: str) -> dict:
    architecture = _architecture()
    suffix = suffix.lower()
    candidates = []
    for asset in release.assets:
        name = asset.get("name")
        if not isinstance(name, str):
            continue
        try:
            _safe_asset_filename(name)
        except UpdateError:
            continue
        if _asset_matches(name, release.version, suffix, architecture):
            candidates.append(asset)
    if len(candidates) != 1:
        raise UpdateError(f"Could not safely identify one {suffix} release asset for this architecture.")
    url = candidates[0].get("browser_download_url")
    if not isinstance(url, str) or not url.startswith("https://github.com/DonGeronimo7/mouse-control/"):
        raise UpdateError("Release asset URL is not from the official Mouse Control repository.")
    return candidates[0]


def _download(asset: dict, destination: Path, opener: Callable = urlopen) -> Path:
    url = asset["browser_download_url"]
    try:
        with opener(Request(url, headers={"User-Agent": "mouse-control-updater"}), timeout=60) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)
    except (URLError, OSError) as exc:
        raise UpdateError("Release download failed; the existing installation was not changed.") from exc
    if not destination.is_file() or destination.stat().st_size == 0:
        raise UpdateError("Downloaded release asset is empty.")
    return destination


def _sudo(command: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return command
    if not shutil.which("sudo"):
        raise UpdateError("This update needs administrator privileges, but sudo is unavailable.")
    return ["sudo", *command]


def _installed_package_version(installation: Installation, run: Callable) -> str | None:
    """Return the installed upstream version, or ``None`` when unverified.

    RPM's VERSION field deliberately excludes its packaging release.  Debian
    versions can include an epoch and Debian revision; neither is part of the
    Mouse Control release tag we compare against.
    """
    package = installation.package or "mouse-control"
    command = (['rpm', '-q', '--qf', '%{VERSION}\\n', package]
               if installation.kind == 'rpm'
               else ['dpkg-query', '-W', '-f=${Version}\\n', package])
    result = run(command)
    if result.returncode:
        return None
    version = result.stdout.strip()
    if installation.kind == "deb":
        version = version.partition(":")[2] if ":" in version else version
        version = version.rsplit("-", 1)[0]
    return version or None


def _package_is_current(installation: Installation, release: Release, run: Callable) -> bool:
    installed = _installed_package_version(installation, run)
    if installed is None:
        return False
    try:
        return Version(installed.lstrip("vV")) >= Version(release.version.lstrip("vV"))
    except InvalidVersion:
        return False


def _package_update(installation: Installation, release: Release, run: Callable = _run,
                    assume_yes: bool = False) -> None:
    if installation.kind == "arch":
        raise UpdateError("This pacman-owned installation is not updated automatically. Update it using the package source that installed it.")
    manager = "dnf" if installation.kind == "rpm" else "apt"
    if not shutil.which(manager):
        raise UpdateError(f"{manager} is unavailable; package-owned files were not changed.")
    package = installation.package or "mouse-control"
    # First let the enabled native repository perform a normal upgrade.
    native = _sudo([manager, "upgrade", *(["--assumeyes"] if assume_yes else []), package] if manager == "dnf"
                   else [manager, "install", "--only-upgrade", package])
    run(native)
    if _package_is_current(installation, release, run):
        return
    # A direct GitHub package can be upgraded safely through the same manager.
    suffix = ".rpm" if installation.kind == "rpm" else ".deb"
    asset = select_asset(release, suffix)
    with tempfile.TemporaryDirectory(prefix="mouse-control-update-") as directory:
        filename = _safe_asset_filename(asset["name"])
        destination = (Path(directory) / filename).resolve()
        if destination.parent != Path(directory).resolve():
            raise UpdateError("Release asset destination escaped its temporary directory.")
        artifact = _download(asset, destination)
        command = [manager, "install", *(["--assumeyes"] if installation.kind == "rpm" and assume_yes else []),
                   str(artifact)]
        result = run(_sudo(command))
    if installation.kind == "rpm":
        installed_current = _package_is_current(installation, release, run)
    else:
        installed_current = not result.returncode and _package_is_current(installation, release, run)
    if not installed_current:
        raise UpdateError(result.stderr.strip() or result.stdout.strip()
                          or "Package manager did not install the requested release.")


def _appimage_update(installation: Installation, release: Release, opener: Callable = urlopen) -> None:
    target = installation.executable
    if not os.access(target.parent, os.W_OK):
        raise UpdateError(f"AppImage cannot be replaced safely. Download the new AppImage manually from GitHub Releases.")
    asset = select_asset(release, ".appimage")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _download(asset, temporary, opener)
        temporary.chmod(target.stat().st_mode)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _shadowed(executable: Path) -> Path | None:
    found = shutil.which("mouse-control")
    if found and Path(found).resolve() != executable:
        return Path(found).resolve()
    return None


def run_update(*, check: bool = False, assume_yes: bool = False, executable: Path | None = None,
               fetcher: Callable[[], Release] = fetch_latest, runner: Callable = _run,
               input_func: Callable[[str], str] = input, opener: Callable = urlopen) -> int:
    installation = detect_installation(executable)
    shadow = _shadowed(installation.executable)
    if shadow:
        print(f"Mouse Control appears to be installed more than once.\nRunning: {installation.executable}\nAlso detected: {shadow}\nThe updater will only update the running installation.")
    try:
        release = fetcher()
    except UpdateError as exc:
        print(f"Could not check for Mouse Control updates.\nYour current installation was not changed.\n\nReason: {exc}", file=sys.stderr)
        return 1
    print(f"Mouse Control Updater\nInstalled: {__version__}\nLatest:    {release.version}\nInstall:   {installation.description}")
    try:
        newer = is_newer(release.version, __version__)
    except UpdateError as exc:
        print(f"Could not check for Mouse Control updates.\nYour current installation was not changed.\n\nReason: {exc}", file=sys.stderr)
        return 1
    if not newer:
        print(f"Mouse Control {__version__} is already up to date.")
        return 0
    print(f"\nUpdate available: {__version__} → {release.version}")
    if check:
        return 0
    if installation.kind in {"unknown", "source"}:
        print("This installation cannot be updated automatically. Update the source checkout normally; no files were changed.", file=sys.stderr)
        return 1
    if not assume_yes:
        try:
            if input_func("Update Mouse Control? [Y/n]: ").strip().lower() not in {"", "y", "yes"}:
                print("Update cancelled.")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("Update cancelled.")
            return 0
    try:
        active = is_service_active()
    except (OSError, subprocess.SubprocessError):
        # systemd --user can be unavailable in a minimal session; that must not
        # prevent a package-manager-owned installation from being updated.
        active = False
    try:
        if installation.kind in {"rpm", "deb", "arch"}:
            _package_update(installation, release, runner, assume_yes=assume_yes)
        elif installation.kind == "appimage":
            _appimage_update(installation, release, opener)
        elif installation.kind == "pip":
            result = runner([sys.executable, "-m", "pip", "install", "--upgrade", "mouse-control"])
            if result.returncode:
                raise UpdateError(result.stderr.strip() or "pip update failed.")
    except UpdateError as exc:
        print(f"Update failed. Your existing installation was not manually replaced.\nReason: {exc}", file=sys.stderr)
        return 1
    print(f"Mouse Control was updated successfully to {release.version}.")
    if active:
        try:
            restart_service()
            print("The previously active service was restarted.")
        except Exception as exc:
            print(f"Update succeeded, but the previously active service could not be restarted: {exc}", file=sys.stderr)
            return 1
    return 0
