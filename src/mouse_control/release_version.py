"""Strict mappings between OMUS release and package versions."""
from __future__ import annotations

from dataclasses import dataclass
import re
import sys


_DISPLAY_VERSION = re.compile(
    r"(?P<version>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)(?:-(?P<release>[1-9]\d*))?"
)


@dataclass(frozen=True, slots=True)
class ReleaseVersion:
    """One release expressed in each packaging system's native fields.

    A display tag may omit the package revision (``0.9.7``) or include it
    (``0.9.7-1``). RPM always receives separate Version and Release fields;
    Python represents an explicit package revision as a PEP 440 post release.
    """

    display: str
    rpm_version: str
    rpm_release: int
    has_explicit_release: bool

    @classmethod
    def parse(cls, value: str) -> "ReleaseVersion":
        display = value.strip()
        if display.startswith(("v", "V")):
            display = display[1:]
        match = _DISPLAY_VERSION.fullmatch(display)
        if match is None:
            raise ValueError(f"unsupported OMUS release version: {value!r}")
        rpm_version = ".".join(
            (match.group("version"), match.group("minor"), match.group("patch"))
        )
        release = match.group("release")
        return cls(
            display=display,
            rpm_version=rpm_version,
            rpm_release=int(release or "1"),
            has_explicit_release=release is not None,
        )

    @property
    def tag(self) -> str:
        return f"v{self.display}"

    @property
    def python_version(self) -> str:
        if self.has_explicit_release:
            return f"{self.rpm_version}.post{self.rpm_release}"
        return self.rpm_version

    def rpm_filename(self, distribution: str, architecture: str) -> str:
        """Return the exact RPM artifact name for explicit package fields."""
        dist = distribution.removeprefix(".")
        if not re.fullmatch(r"[A-Za-z0-9_+~]+", dist):
            raise ValueError(f"invalid RPM distribution suffix: {distribution!r}")
        if not re.fullmatch(r"[A-Za-z0-9_]+", architecture):
            raise ValueError(f"invalid RPM architecture: {architecture!r}")
        return (
            f"omus-{self.rpm_version}-{self.rpm_release}."
            f"{dist}.{architecture}.rpm"
        )

    def match_rpm_filename(self, filename: str) -> re.Match[str] | None:
        """Match only this release's RPM Version/Release and safe suffix fields."""
        return re.fullmatch(
            rf"(?:omus|mouse-control)-{re.escape(self.rpm_version)}-{self.rpm_release}"
            rf"(?:\.[A-Za-z0-9_+~]+)*\.(?P<architecture>[A-Za-z0-9_]+)\.rpm",
            filename,
        )


def main(argv: list[str] | None = None) -> int:
    """Print one package field for release automation without shell parsing."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 2:
        print(
            "usage: python -m mouse_control.release_version VERSION "
            "{display,tag,python-version,rpm-version,rpm-release}",
            file=sys.stderr,
        )
        return 2
    try:
        version = ReleaseVersion.parse(arguments[0])
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    fields = {
        "display": version.display,
        "tag": version.tag,
        "python-version": version.python_version,
        "rpm-version": version.rpm_version,
        "rpm-release": str(version.rpm_release),
    }
    value = fields.get(arguments[1])
    if value is None:
        print(f"unknown release field: {arguments[1]!r}", file=sys.stderr)
        return 2
    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
