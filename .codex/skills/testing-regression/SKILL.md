# Skill: Mouse Control Testing and Regression

## When to use

Use this skill for:

- any multi-file implementation,
- runtime behavior changes,
- hardware-backend changes,
- reconnect/lifecycle changes,
- notification changes,
- remapper changes,
- Automatic Discovery changes,
- release-readiness checks,
- architecture refactors.

The goal is not merely “tests pass”. The goal is to prove the intended behavior without weakening existing contracts.

## Testing philosophy

Prefer behavioral tests over source-string tests.

A good regression test proves an externally meaningful property such as:

- no write occurred,
- exact state was emitted,
- one notification was generated,
- remapping survived reconnect,
- ambiguity was refused,
- an old behavior remained unchanged.

Avoid tests that merely assert that a helper function exists or a particular source line appears.

## Development loop

Use this order:

```text
inspect current behavior
→ add/adjust focused test
→ implement smallest coherent change
→ run focused tests
→ inspect failures
→ correct root cause
→ run related subsystem tests
→ run full suite
→ compileall
→ diff check
→ inspect final diff
```

Do not stop after targeted tests.

## Required base validation

Before handoff:

```bash
git diff --check
python -m compileall -q src tests
PYTHONPATH=src pytest -q
```

Record the exact results.

## Focused suites for Automatic Discovery

When relevant, include:

```bash
PYTHONPATH=src pytest -q     tests/test_calibrated_profiles.py     tests/test_deep_stage_learning.py     tests/test_transition_sources.py     tests/test_discovery_backend.py     tests/test_hardware_supervisor.py     tests/test_remapper_reconnect.py     tests/test_notifications.py     tests/test_dpi_cycle.py
```

Also include any new runtime-specific test files.

## Regression domains

For architecture changes, deliberately verify these domains.

### Remapping

Check:

- passthrough,
- button remaps,
- key remaps,
- chords,
- dpi-cycle mapping,
- disconnect/reconnect,
- no stuck uinput keys/buttons.

### DPI writes

Check:

- PROVEN software cycling still writes,
- unproven/read-only paths never write,
- failed writes do not corrupt desired state,
- readback mismatch is handled.

### DPI observation

Check:

- confirmed state,
- absolute state decoding,
- trigger progression,
- duplicate suppression,
- rapid ordering,
- wraparound,
- unsynchronized trigger refusal.

### Notifications

Check:

- one transition → one popup,
- deliberate software cycles are not accidentally deduplicated,
- wraparound can repeat an old DPI and still notify,
- DBus failure does not stop hardware/remapping behavior.

### Reconnect

Check:

- live node renumbering,
- generation/rebind semantics,
- read-only trigger synchronization invalidation,
- absolute resynchronization,
- remapper recovery,
- no stale session reuse.

### Identity and ambiguity

Check:

- exact device reuse,
- different device refusal,
- ambiguous match refusal,
- corrupt profile refusal,
- volatile path not persisted.

### Compatibility

Check:

- schema-v1 calibrated profiles still load,
- G305 HID++ behavior remains unchanged,
- PROVEN learned actions remain unchanged,
- learned polling behavior remains unchanged.

## Safety assertions

For read-only discovery work, include explicit negative tests.

Examples:

```python
backend.set_dpi = Mock()
# exercise calibrated read-only transition
backend.set_dpi.assert_not_called()
```

Or patch the relevant lower-level writer and assert it is never reached.

Do not rely solely on architectural reasoning for “no write” claims when a deterministic test can prove the call path.

## Test naming

Use names that state behavior, for example:

- `test_unsynchronized_trigger_does_not_invent_stage`
- `test_reconnect_invalidates_trigger_only_cursor`
- `test_absolute_source_resynchronizes_after_reconnect`
- `test_read_only_transition_never_calls_set_dpi`

Avoid vague names such as:

- `test_runtime`
- `test_new_behavior`
- `test_tracker`

## Hardware validation boundary

Automated tests can prove software behavior.

They cannot prove:

- a physical mouse emits the assumed packet,
- a write changes real hardware,
- timing is correct on a real receiver,
- a specific new device is supported.

Only user-observed real-device testing may be labeled `Physically validated`.

Keep these levels separate in every report.

## Failure handling

If full pytest exposes an unrelated existing failure:

1. establish whether the failure exists at starting HEAD,
2. report that evidence,
3. do not silently broaden the task,
4. fix it only if the current change caused or exposed it in a directly relevant way.

If the current change causes a regression, resolve it before handoff.

## Packaging checks

For release-adjacent or packaging-sensitive work, additionally consider:

- wheel/sdist build,
- Fedora RPM build,
- package `%check`,
- installed CLI smoke test.

Do not run release/tagging actions unless explicitly requested.

## Commit checkpoint rule

A logical architectural checkpoint is ready to commit only when:

- intended focused tests pass,
- relevant regression suites pass,
- full pytest passes,
- compileall passes,
- `git diff --check` passes,
- final diff has been inspected,
- no unrelated file changes are present.

Prefer several coherent green commits over one giant mixed commit.
