# Hardware compatibility matrix

Only physically validated or community-reported results belong here.

| Manufacturer | Model | VID:PID | Distribution | Install package | Remapping | Discovery read-side DPI | Native DPI control | DPI notifications | Polling control | Runtime hardware surface | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Logitech | G305 | 046d:4074 | Fedora 44 | v0.9.0 | validated | validated | validated reference adapter + PROVEN exact-model learned DPI | validated | validated reference adapter + PROVEN exact-model learned polling | Automatic Discovery | v0.9.0 validated reference | Automatic Discovery retains the G305 as the physically validated reference. Exact-model learned DPI and report-rate operations were promoted only after readback, independent physical verification, persistent-session proof where required, and exact rollback. The learned DPI-cycle action trigger remains read-only evidence; native HID++ remains a proven teacher/adapter. No learned write authority is generalized to other mouse models. |
