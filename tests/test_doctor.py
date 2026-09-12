from mouse_control import doctor
from mouse_control.discovery import MouseDevice


def test_report_is_privacy_safe(monkeypatch, capsys):
    mouse = MouseDevice("Test Mouse", "/dev/input/event9", vendor=0x046D, product=0x4074)
    assert doctor.print_doctor(report=True, mice=[mouse]) == 0
    output = capsys.readouterr().out
    assert "/dev/input/event9" not in output
    assert "046d:4074" in output
    assert "Privacy:" in output


def test_package_manager_detection(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/bin/dnf" if name == "dnf" else None)
    assert doctor.package_manager() == "dnf"


def test_unsupported_package_manager_is_safe(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "package_manager", lambda: None)
    assert doctor.doctor_fix(lambda _: "y") == 0
    assert "no changes made" in capsys.readouterr().out.lower()


def test_declined_fix_causes_no_mutation(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "package_manager", lambda: "apt")
    assert doctor.doctor_fix(lambda _: "n") == 0
    assert "No changes made." in capsys.readouterr().out


def test_hardware_backend_is_not_probed_by_read_only_doctor(monkeypatch):
    mouse = MouseDevice("Unknown mouse", "/ignored", vendor=1, product=2)
    assert "not probed" in "\n".join(doctor._mouse_lines([mouse]))
