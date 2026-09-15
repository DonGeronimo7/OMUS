# AI Development Handoff Log

This is the concise chronological coordination trail between ChatGPT and Codex.
Read `docs/AI_HANDOFF_PROTOCOL.md` for the full protocol and
`docs/PROJECT_STATUS.md` for authoritative architectural status.

## 2026-09-14 — Protocol established

- ChatGPT and Codex now coordinate through committed Git state rather than chat
  memory alone.
- ChatGPT is the project manager/reviewer; Codex is the primary implementation
  engineer for handed-off coding tasks.
- Codex startup must read `AGENTS.md`, `docs/AI_HANDOFF_PROTOCOL.md`,
  `docs/PROJECT_STATUS.md`, and the latest entry here before implementation.
- Every Codex implementation handoff must identify branch/commit, files and
  behavior changed, automated and physical validation, remaining risks, and the
  next bounded task.
- Validation claims are explicitly separated into code-reviewed, unit-tested,
  integration-tested, physically validated, and unverified.
- Repository state and physical evidence take precedence over stale chat
  descriptions.

### Current coordination focus

The active investigation is native Logitech HID++ Report Rate (`0x8060`) write
behavior on the physically validated G305. Read capability and supported-rate
discovery are established; do not claim native polling-rate write completion
until a real G305 rate transition is independently confirmed by protocol
readback/confirmation and physical testing. Preserve evdev remapping and avoid
unsafe persistent onboard-profile writes while investigating.
