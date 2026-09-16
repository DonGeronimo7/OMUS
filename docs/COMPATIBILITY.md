# Hardware compatibility matrix

Only physically validated or community-reported results belong here.

| Manufacturer | Model | VID:PID | Distribution | Install package | Remapping | DPI hardware control | DPI notifications | Polling control | Backend | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Logitech | G305 | 046d:4074 | Fedora 44 | RPM | validated | needs native revalidation | needs native revalidation | needs native revalidation | Native HID++ 2 | protocol-tested; hardware revalidation pending | Native DPI and report-rate read/write verification plus actual-DPI event resolution are implemented; persistent stages remain unclaimed. |
| Logitech | G305 | 046d:4074 | Fedora 44 | source checkout | validated | read-only learned states | validated | measured ~1000 Hz, read-only | Automatic Discovery | physically validated | With HID++/vendor backends bypassed, calibrated discovery learned raw states `0..4` as `800/1500/2000/2500/3000 DPI`, confirmed the wrap back to 800 through physical CPI measurement, persisted the path-independent mapping, rebound it at runtime, and reproduced the complete DPI event sequence. Unknown HID writes remained forbidden. |
