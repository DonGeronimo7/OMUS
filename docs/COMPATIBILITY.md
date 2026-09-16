# Hardware compatibility matrix

Only physically validated or community-reported results belong here.

| Manufacturer | Model | VID:PID | Distribution | Install package | Remapping | Discovery read-side DPI | Native DPI control | DPI notifications | Polling control | Runtime hardware surface | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Logitech | G305 | 046d:4074 | Fedora 44 | source/feature branch | validated | validated | validated reference adapter | validated | validated reference adapter | Automatic Discovery | controlled Discovery proof complete | Teacher-free calibrated Discovery learned raw states 0..4 as 800/1500/2000/2500/3000 DPI, confirmed wrap and ~1000 Hz, persisted the read-only mapping, rebound it at runtime, and produced the full live DPI sequence with vendor/native backends bypassed. Native HID++ remains the proven write-capable adapter; learned writes remain forbidden. |
