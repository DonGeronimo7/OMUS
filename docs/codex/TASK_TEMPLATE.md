# Codex Task Template — Mouse Control

## Goal

Describe the exact observable result.

## Branch

`feat/...`

Do not modify `main`.

## Starting point

Expected HEAD:

`<sha>`

Verify remote branch state before changing code.

## Read first

- `AGENTS.md`
- `docs/AI_HANDOFF_PROTOCOL.md`
- `docs/PROJECT_STATUS.md`
- latest relevant `docs/AI_HANDOFF_LOG.md`
- relevant `.codex/skills/.../SKILL.md`

## Current evidence

Record only demonstrated facts:

- code behavior,
- test results,
- hardware observations,
- captured logs.

Separate hypotheses clearly.

## Scope

May change:

- `...`

Prefer the smallest complete architecture change.

## Do not change

- v0.8.2 compatibility behavior
- existing proven backend semantics
- unrelated UI/service/remapping behavior
- release metadata unless task explicitly requires it

## Safety constraints

State task-specific constraints.

For hardware work, always include:

- unknown HID remains read-only unless independently PROVEN,
- calibrated evidence never grants write authority,
- ambiguity must refuse,
- volatile `/dev/*` nodes are not persistent identity.

## Acceptance criteria

Use behavioral criteria.

Examples:

- one physical trigger produces one confirmed observed DPI state,
- no `set_dpi()` call occurs,
- reconnect invalidates trigger-only synchronization,
- full test suite passes.

## Validation

Run focused suites first, then:

```bash
git diff --check
python -m compileall -q src tests
PYTHONPATH=src pytest -q
```

## Git discipline

- logical commits,
- no merge,
- no tag,
- no release,
- no history rewrite,
- push only the assigned feature branch.

## Final report

Use:

`docs/codex/HANDOFF_TEMPLATE.md`
