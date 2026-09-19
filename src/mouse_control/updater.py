"""Safe, explicit update dispatch for OMUS and legacy installations.

This deliberately delegates to the mechanism which owns the running copy; it
never replaces files owned by a system package manager.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from packaging.version import InvalidVersion, Version

from . import __version__
from .release_version import ReleaseVersion
from .service import is_service_active, restart_service

RELEASE_URL = "https://api.github.com/repos/DonGeronimo7/OMUS/releases/latest"
REPOSITORY = "DonGeronimo7/OMUS"
CHECKSUMS_NAME = "SHA256SUMS"
_DOWNLOAD_HOSTS = frozenset({"github.com", "objects.githubusercontent.com"})


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


@dataclass(frozen=True)
class UpdateStatus:
    """One explicit, read-only release check and its safe update policy."""

    installed_version: str
    available_version: str
    update_available: bool
    installation: Installation
    release: Release
    update_supported: bool
    unavailable_reason: str = ""


def is_newer(latest: str, installed: str) -> bool:
    """Compare release tags with PEP 440 parsing, never mixed Python types."""
    try:
        return Version(latest.strip().lstrip("vV")) > Version(installed.strip().lstrip("vV"))
    except InvalidVersion as exc:
        raise UpdateError(f"Unsupported release version: {exc}") from exc


def _run_capture(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a command whose stdout/stderr OMUS must inspect."""
    return subprocess.run(args, text=True, capture_output=True, **kwargs)  # type: ignore[arg-type]


def _run_interactive(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run a terminal-owned command with inherited stdin/stdout/stderr."""
    return subprocess.run(args, text=True, **kwargs)  # type: ignore[arg-type]


def _run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """Compatibility alias for captured query commands."""
    return _run_capture(args, **kwargs)


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
        try:
            dist = importlib.metadata.distribution("omus")
            distribution_name = "omus"
        except importlib.metadata.PackageNotFoundError:
            dist = importlib.metadata.distribution("mouse-control")
            distribution_name = "mouse-control"
        direct = dist.read_text("direct_url.json")
        if direct and json.loads(direct).get("dir_info", {}).get("editable"):
            return Installation("source", executable, detail="editable pip install")
        return Installation("pip", executable, distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return Installation("unknown", executable)
    except (json.JSONDecodeError, OSError):
        return Installation("source", executable, detail="unverifiable Python source install")


def fetch_latest(url: str = RELEASE_URL, opener: Callable = urlopen) -> Release:
    if url != RELEASE_URL:
        raise UpdateError("Release information URL is not the official OMUS endpoint.")
    try:
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "omus-updater"})
        with opener(request, timeout=10) as response:
            _validate_response_url(response, expected_host="api.github.com")
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


def _validate_response_url(response: object, *, expected_host: str | None = None) -> None:
    """Reject downgrade and cross-origin redirects before consuming a response."""
    geturl = getattr(response, "geturl", None)
    if geturl is None:  # Small deterministic test doubles have no redirect state.
        return
    final_url = geturl()
    parsed = urlparse(final_url)
    allowed = {expected_host} if expected_host else set(_DOWNLOAD_HOSTS)
    if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password:
        raise UpdateError("Release download was redirected to an untrusted source.")


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
    """Match canonical OMUS and v0.9.9-era release filenames."""
    escaped_version = re.escape(version.lstrip("vV"))
    if suffix == ".rpm":
        try:
            match = ReleaseVersion.parse(version).match_rpm_filename(name)
        except ValueError:
            return False
        return bool(match and (match.group("architecture") == "noarch"
                               or _normalize_architecture(match.group("architecture"))
                               == architecture))
    if suffix == ".deb":
        match = re.fullmatch(rf"(?:omus|mouse-control)_{escaped_version}_([^_]+)\.deb", name)
        return bool(match and (match.group(1) == "all"
                               or _normalize_architecture(match.group(1)) == architecture))
    if suffix == ".appimage":
        match = re.fullmatch(rf"(?:OMUS|Mouse-Control)-{escaped_version}-(.+)\.AppImage", name)
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
    expected_prefix = f"https://github.com/{REPOSITORY}/releases/download/v{release.version}/"
    if not isinstance(url, str) or url != expected_prefix + candidates[0]["name"]:
        raise UpdateError("Release asset URL is not from the official OMUS repository.")
    return candidates[0]


def inspect_update(
    *,
    installation: Installation | None = None,
    executable: Path | None = None,
    fetcher: Callable[[], Release] | None = None,
) -> UpdateStatus:
    """Perform one explicit check without modifying the installation.

    Release lookup, version parsing, installation ownership, and AppImage
    compatibility remain updater-owned so presentation layers do not reproduce
    updater policy.
    """

    installation = installation or detect_installation(executable)
    release = (fetcher or fetch_latest)()
    update_available = is_newer(release.version, __version__)
    supported = installation.kind in {"rpm", "deb", "appimage", "pip"}
    reason = ""
    if installation.kind == "source":
        reason = "Source/development checkouts must be updated through their source workflow."
    elif installation.kind == "unknown":
        reason = "The installation owner is unknown, so automatic replacement is disabled."
    elif installation.kind == "arch":
        reason = "This pacman-owned installation must be updated through its package source."
    elif installation.kind == "appimage" and update_available:
        try:
            select_asset(release, ".appimage")
        except UpdateError as exc:
            supported = False
            reason = str(exc)
    return UpdateStatus(
        installed_version=__version__,
        available_version=release.version,
        update_available=update_available,
        installation=installation,
        release=release,
        update_supported=supported,
        unavailable_reason=reason,
    )


def _checksum_asset(release: Release) -> dict:
    matches = [asset for asset in release.assets if asset.get("name") == CHECKSUMS_NAME]
    if len(matches) != 1:
        raise UpdateError("Release must contain exactly one SHA256SUMS asset.")
    asset = matches[0]
    expected = f"https://github.com/{REPOSITORY}/releases/download/v{release.version}/{CHECKSUMS_NAME}"
    if asset.get("browser_download_url") != expected:
        raise UpdateError("Checksum manifest URL is not from the official OMUS release.")
    return asset


def _parse_checksums(data: bytes) -> dict[str, str]:
    """Parse a strict, path-free GNU sha256sum manifest."""
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise UpdateError("Checksum manifest is not valid ASCII.") from exc
    checksums: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([^\s]+)", line)
        if match is None:
            raise UpdateError("Checksum manifest is malformed.")
        digest, filename = match.groups()
        _safe_asset_filename(filename)
        if filename in checksums:
            raise UpdateError("Checksum manifest contains a duplicate filename.")
        checksums[filename] = digest.lower()
    if not checksums:
        raise UpdateError("Checksum manifest is empty.")
    return checksums


def _download_bytes(asset: dict, *, opener: Callable = urlopen, limit: int = 1024 * 1024) -> bytes:
    url = asset["browser_download_url"]
    try:
        with opener(Request(url, headers={"User-Agent": "omus-updater"}), timeout=30) as response:
            _validate_response_url(response)
            data = response.read(limit + 1)
    except (URLError, OSError, ValueError) as exc:
        raise UpdateError("Release checksum manifest could not be retrieved.") from exc
    if len(data) > limit:
        raise UpdateError("Checksum manifest is unexpectedly large.")
    return data


def _expected_checksum(release: Release, filename: str, *, opener: Callable = urlopen) -> str:
    checksums = _parse_checksums(_download_bytes(_checksum_asset(release), opener=opener))
    if filename not in checksums:
        raise UpdateError("Selected release artifact is missing from SHA256SUMS.")
    expected_names = {
        asset.get("name") for asset in release.assets
        if isinstance(asset.get("name"), str) and asset.get("name") != CHECKSUMS_NAME
    }
    if set(checksums) != expected_names:
        raise UpdateError("SHA256SUMS contains a missing or unexpected release asset.")
    return checksums[filename]


def _download(asset: dict, destination: Path, opener: Callable = urlopen) -> Path:
    url = asset["browser_download_url"]
    try:
        with opener(Request(url, headers={"User-Agent": "omus-updater"}), timeout=60) as response:
            _validate_response_url(response)
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)
    except (URLError, OSError) as exc:
        raise UpdateError("Release download failed; the existing installation was not changed.") from exc
    if not destination.is_file() or destination.stat().st_size == 0:
        raise UpdateError("Downloaded release asset is empty.")
    return destination


def _download_verified(release: Release, asset: dict, destination: Path,
                       opener: Callable = urlopen) -> Path:
    filename = _safe_asset_filename(asset["name"])
    expected = _expected_checksum(release, filename, opener=opener)
    artifact = _download(asset, destination, opener)
    digest = hashlib.sha256()
    with artifact.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if not digest.hexdigest() == expected:
        raise UpdateError("Downloaded release artifact failed SHA-256 verification.")
    return artifact


def _sudo(command: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return command
    if not shutil.which("sudo"):
        raise UpdateError("This update needs administrator privileges, but sudo is unavailable.")
    return ["sudo", *command]


def _installed_package_version(installation: Installation, run_capture: Callable) -> str | None:
    """Return the installed upstream version, or ``None`` when unverified.

    Incremental release tags include the package revision, so RPM and Debian
    queries retain it. RPM's distro suffix is removed before PEP 440 ordering.
    """
    package = installation.package or "omus"
    command = (['rpm', '-q', '--qf', '%{VERSION}-%{RELEASE}\\n', package]
               if installation.kind == 'rpm'
               else ['dpkg-query', '-W', '-f=${Version}\\n', package])
    result = run_capture(command)
    if result.returncode:
        return None
    version = result.stdout.strip()
    if installation.kind == "rpm":
        version = re.sub(r"(?<=-\d)(?:\.[A-Za-z0-9_]+)+$", "", version)
    else:
        version = version.partition(":")[2] if ":" in version else version
    return version or None


def _package_is_current(installation: Installation, release: Release,
                        run_capture: Callable) -> bool:
    installed = _installed_package_version(installation, run_capture)
    if installed is None and installation.kind in {"rpm", "deb"} and installation.package != "omus":
        installed = _installed_package_version(
            Installation(installation.kind, installation.executable, "omus"), run_capture)
    if installed is None:
        return False
    try:
        return Version(installed.lstrip("vV")) >= Version(release.version.lstrip("vV"))
    except InvalidVersion:
        return False


def _package_error(result: subprocess.CompletedProcess[str]) -> str:
    """Return captured diagnostics when available, otherwise a safe generic error."""
    stderr = getattr(result, "stderr", None) or ""
    stdout = getattr(result, "stdout", None) or ""
    return stderr.strip() or stdout.strip() or "Package manager did not install the requested release."


def _package_update(installation: Installation, release: Release,
                    run: Callable | None = None, assume_yes: bool = False, *,
                    run_capture: Callable | None = None,
                    run_interactive: Callable | None = None,
                    opener: Callable = urlopen) -> None:
    # ``run`` is retained as a compatibility injection point for existing tests
    # and callers. Production code leaves it unset and uses distinct captured
    # and terminal-owned execution paths.
    if run is not None:
        run_capture = run_capture or run
        run_interactive = run_interactive or run
    run_capture = run_capture or _run_capture
    run_interactive = run_interactive or _run_interactive
    if installation.kind == "arch":
        raise UpdateError("This pacman-owned installation is not updated automatically. Update it using the package source that installed it.")
    manager = "dnf" if installation.kind == "rpm" else "apt"
    if not shutil.which(manager):
        raise UpdateError(f"{manager} is unavailable; package-owned files were not changed.")
    package = installation.package or "omus"
    yes_args = (["--assumeyes"] if manager == "dnf" else ["--yes"]) if assume_yes else []

    if not assume_yes:
        print(f"\nStarting {manager.upper()}.\nReview the transaction below before approving it.", flush=True)

    # First let the enabled native repository perform a normal upgrade. Package
    # manager transactions inherit the user's terminal; only follow-up version
    # queries are captured for programmatic verification.
    native = _sudo([manager, "upgrade", *yes_args, package] if manager == "dnf"
                   else [manager, "install", "--only-upgrade", *yes_args, package])
    run_interactive(native)
    if _package_is_current(installation, release, run_capture):
        return

    # A direct GitHub package can be upgraded safely through the same manager.
    suffix = ".rpm" if installation.kind == "rpm" else ".deb"
    asset = select_asset(release, suffix)
    with tempfile.TemporaryDirectory(prefix="omus-update-") as directory:
        filename = _safe_asset_filename(asset["name"])
        destination = (Path(directory) / filename).resolve()
        if destination.parent != Path(directory).resolve():
            raise UpdateError("Release asset destination escaped its temporary directory.")
        artifact = _download_verified(release, asset, destination, opener)
        command = [manager, "install", *yes_args, str(artifact)]
        result = run_interactive(_sudo(command))
    if installation.kind == "rpm":
        installed_current = _package_is_current(installation, release, run_capture)
    else:
        installed_current = not result.returncode and _package_is_current(
            installation, release, run_capture)
    if not installed_current:
        raise UpdateError(_package_error(result))


def _appimage_update(installation: Installation, release: Release, opener: Callable = urlopen) -> None:
    target = installation.executable
    try:
        original = target.lstat()
    except OSError as exc:
        raise UpdateError("AppImage target could not be inspected safely.") from exc
    if not target.is_file() or target.is_symlink():
        raise UpdateError("AppImage target must be a regular, non-symlink file.")
    if not os.access(target.parent, os.W_OK):
        raise UpdateError(f"AppImage cannot be replaced safely. Download the new AppImage manually from GitHub Releases.")
    asset = select_asset(release, ".appimage")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _download_verified(release, asset, temporary, opener)
        current = target.lstat()
        if (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
            raise UpdateError("AppImage target changed during the update; replacement was refused.")
        temporary.chmod(original.st_mode & 0o777)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _shadowed(executable: Path) -> Path | None:
    found = shutil.which("omus") or shutil.which("mouse-control")
    if found and Path(found).resolve() != executable:
        return Path(found).resolve()
    return None


def run_update(*, check: bool = False, assume_yes: bool = False, executable: Path | None = None,
               fetcher: Callable[[], Release] = fetch_latest, runner: Callable = _run_capture,
               interactive_runner: Callable | None = None,
               input_func: Callable[[str], str] = input, opener: Callable = urlopen) -> int:
    installation = detect_installation(executable)
    shadow = _shadowed(installation.executable)
    if shadow:
        print(f"OMUS appears to be installed more than once.\nRunning: {installation.executable}\nAlso detected: {shadow}\nThe updater will only update the running installation.")
    try:
        inspected = inspect_update(installation=installation, fetcher=fetcher)
    except UpdateError as exc:
        print(f"Could not check for OMUS updates.\nYour current installation was not changed.\n\nReason: {exc}", file=sys.stderr)
        return 1
    release = inspected.release
    print(f"OMUS Updater\nInstalled: {__version__}\nLatest:    {release.version}\nInstall:   {installation.description}")
    if not inspected.update_available:
        print(f"OMUS {__version__} is already up to date.")
        return 0
    print(f"\nUpdate available: {__version__} → {release.version}")
    if check:
        return 0
    if installation.kind in {"unknown", "source"}:
        print("This installation cannot be updated automatically. Update the source checkout normally; no files were changed.", file=sys.stderr)
        return 1
    if not assume_yes:
        try:
            if input_func("Update OMUS? [Y/n]: ").strip().lower() not in {"", "y", "yes"}:
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
            package_interactive_runner = interactive_runner
            if package_interactive_runner is None:
                package_interactive_runner = (_run_interactive if runner is _run_capture
                                              else runner)
            _package_update(installation, release, assume_yes=assume_yes,
                            run_capture=runner, run_interactive=package_interactive_runner,
                            opener=opener)
        elif installation.kind == "appimage":
            _appimage_update(installation, release, opener)
        elif installation.kind == "pip":
            result = runner([sys.executable, "-m", "pip", "install", "--upgrade", "omus"])
            if result.returncode:
                raise UpdateError(result.stderr.strip() or "pip update failed.")
    except KeyboardInterrupt:
        print("\nUpdate cancelled.")
        return 0
    except UpdateError as exc:
        print(f"Update failed. Your existing installation was not manually replaced.\nReason: {exc}", file=sys.stderr)
        return 1
    print(f"OMUS was updated successfully to {release.version}.")
    if active:
        try:
            restart_service()
            print("The previously active service was restarted.")
        except Exception as exc:
            print(f"Update succeeded, but the previously active service could not be restarted: {exc}", file=sys.stderr)
            return 1
    return 0
