# Credits, protocol provenance, and license review

OMUS stands on years of public Linux input and mouse-protocol research.
Its distinct contribution is to combine that knowledge with structural HID
interpretation, behavioral observation, evidence tracking, and conservative
automatic discovery. It does not claim to have independently discovered every
protocol fact listed below.

This file is a provenance record, not legal advice. It distinguishes a cited
protocol source from source code that is copied, adapted, translated, or
vendored. A cited protocol fact is not automatically a licensed code inclusion;
conversely, any future import of upstream expression must retain the applicable
copyright and license notices before distribution.

## Current audit result

The current source tree contains no vendored third-party source tree, generated
upstream table, or retained upstream copyright header. The relevant current
modules were introduced as OMUS files in Git history. Their known
external inputs are protocol research, documentation, public implementation
behavior, and hardware evidence, recorded below.

This is evidence from the checked repository and its Git history, not a
forensic proof that a particular constant or algorithm was never translated
from an upstream work. The unresolved items at the end remain maintainer-review
requirements. No conclusion here changes the `AGPL-3.0-or-later` license for
the current OMUS development tree or substitutes for advice from qualified
counsel. Historical versions remain under the licenses applicable when they
were distributed.

## Protocol and research credits

| Project or source | Contribution represented here | Current OMUS location | Public license / review state |
| --- | --- | --- | --- |
| [OpenRazer](https://github.com/openrazer/openrazer) | Razer 90-byte RPC envelope, command behavior, exact-product protocol research, and physical reports. | `src/mouse_control/native_razer.py`; `protocol_repertoire.py` | GitHub currently reports GPL-2.0. OMUS has no OpenRazer runtime dependency or vendored OpenRazer file. Preserve upstream notices if code or expressive tables are ever imported. |
| [libratbag](https://github.com/libratbag/libratbag) | ASUS ROG command-family and Sinowealth/ODM configuration-blob research. | `src/mouse_control/protocol_repertoire.py` | GitHub currently reports MIT. Current use is cited family facts for recognition; the Sinowealth entry is write-disabled. |
| [rivalcfg](https://github.com/flozz/rivalcfg) | SteelSeries command and device-definition research. | `src/mouse_control/protocol_repertoire.py` | GitHub currently reports WTFPL. Current use is cited family facts only; no SteelSeries runtime driver is shipped. |
| [OpenSharkX11](https://github.com/clevim/OpenSharkX11) | Attack Shark X11 report shapes, safety warning for report `0x0b`, and hardware observations. | `src/mouse_control/protocol_repertoire.py` | Upstream describes itself as MIT. OMUS records recognition facts and keeps all generic writes disabled. |
| [OpenMouse mouse-protocol](https://github.com/OpenMouse-Project/mouse-protocol) | Attack Shark X11 and MCHOSE transaction/reply research; Redragon M724 Feature-report/session, DPI/polling, open/commit/close, and upstream physical-write observations (`b7183b395b2b0350c1e50cbcd9616c56f8de2e7a`, `73f57898340636e0a0fdab8ce8f517449e065e33`); Ryunix Kyu Pro MX1 telemetry structure (`37739057a4b1a5484d8e131f1a6b47d753cad7ce`). | `src/mouse_control/protocol_repertoire.py`; Razer source comment | No top-level license file was identified by this audit. Treat protocol references as citation-only until a maintainer records a pinned upstream license and confirms the scope of any adaptation. No upstream implementation, expressive table, or test vector is vendored. |
| [AJAZZ Control Center](https://github.com/Aiacos/ajazz-control-center) | AJ-series feature-report envelope and hardware observations. | `src/mouse_control/protocol_repertoire.py` | GitHub license metadata is currently absent. The present entry is a write-gated recognition record; review the upstream license and source pin before importing any implementation or table. |
| [LAMZU Aurora](https://www.lamzu.net/#/project/items) | Vendor catalog and web-application behavior for the modern 64-byte Feature-0/Input-4 family, legacy VID `3554` report-8 family, Thorn identities, commands, events, dependencies, timing priors, and dangerous-operation boundaries. | `src/mouse_control/lamzu_aurora.py`; `protocol_repertoire.py` | Facts were captured from Aurora 1.0.32 vendor resources on 2026-09-18 and independently expressed as declarative knowledge and tests. This is `VENDOR_DECLARED`/`VENDOR_IMPLEMENTED`, not hardware verification. No vendor bundle or copied source is distributed; exact-model writes remain disabled. |
| [Solaar](https://github.com/pwr-Solaar/Solaar) | Reviewed for public HID++ background and device/protocol context. | No current source-level dependency or cited implementation found. | GitHub currently reports GPL-2.0. It is not presented as a code source in this release. |
| Linux HID/input maintainers, the [HID Usage Tables](https://usb.org/document-library/hid-usage-tables-15), and [libevdev](https://gitlab.freedesktop.org/libevdev/libevdev) | Platform APIs, standard HID semantics, and evdev behavior on which OMUS operates. | HID/evdev integration throughout `src/mouse_control` | No Linux, HID-tools, or libevdev source files are bundled. Standards and kernel interfaces are not treated as vendor-protocol write authority. |

The repertoire also contains a `bitmouse-72` synthetic semantic fixture. Its
current record identifies only “source-derived semantic fixture”; it has no
traceable upstream repository or copyright owner in this checkout. It is
passive recognition-only (`WriteScope.NEVER`) and must remain that way until
the maintainer records its original source and license status.

## What the project distributes

OMUS distributes its first-party current source under `AGPL-3.0-or-later` and
the repository's `LICENSE`. This credits file is included in source
distributions and installed documentation for RPM, Debian, Arch, and AppImage
artifacts so downstream users can inspect the provenance record.

The audit did not find a copied or vendored upstream work whose full license
text must be included in the current artifacts. That finding is conditional on
the source-level review above. If an upstream file, substantial expressive
table, comment, test vector, or translation is added later, do all of the
following in the same change:

1. retain the upstream copyright and license notice exactly as required;
2. identify the upstream file, revision, and license in this document;
3. add any required third-party license text to the source and binary packages;
4. confirm that the combined distribution is compatible with
   `AGPL-3.0-or-later`;
5. add a focused packaging regression check.

## Maintainer review queue

- Establish the original source, author, and license for the `bitmouse-72`
  fixture before treating it as anything beyond a synthetic, write-disabled
  test grammar.
- For OpenMouse mouse-protocol and AJAZZ Control Center, record a stable source
  revision and applicable license before importing code, tables, test vectors,
  or documentation text.
- Re-review `native_razer.py` and every repertoire entry against its cited
  source before asserting that a future change is clean-room or independently
  implemented. Git history alone cannot settle expression-level derivation.
- Add a source-level notice and bundled upstream license material whenever a
  future review finds copied, adapted, translated, or substantially derived
  content.
