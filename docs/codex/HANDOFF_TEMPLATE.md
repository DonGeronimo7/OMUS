# Codex → ChatGPT Implementation Handoff

Use this template at the end of every substantial OMUS implementation task.

---

## HANDOFF

### Goal

State the observable engineering goal in one or two sentences.

### Repository state

- Branch:
- Starting HEAD:
- Final HEAD:
- Working tree:
- Remote branch verified before push: yes/no

### Commits created

- `<sha>` — `<message>`

### Files changed

- `path`
- `path`

### Architecture / behavior changed

Describe:

- what changed,
- which path owns the new behavior,
- which existing paths were deliberately left unchanged.

### Safety boundaries

Explicitly state:

- whether any new write path was added,
- what grants write authority,
- what remains read-only,
- how ambiguity is handled.

For Automatic Discovery work also state:

- whether calibrated transition sources can write,
- whether the new path can call `set_dpi`,
- whether desired hardware state is updated by observed-only events.

### Compatibility

Confirm the status of:

- v0.8.2 compatibility contract,
- G305 HID++,
- PROVEN learned DPI operations,
- learned polling,
- remapping,
- reconnect,
- notifications.

Do not claim compatibility without test evidence.

### Validation

#### Focused tests

Command:

```bash
...
```

Result:

```text
...
```

#### Full test suite

Command:

```bash
PYTHONPATH=src pytest -q
```

Result:

```text
...
```

#### Compile

```bash
python -m compileall -q src tests
```

Result:

```text
...
```

#### Diff validation

```bash
git diff --check
```

Result:

```text
...
```

#### Packaging

State whether wheel/RPM/package validation was run.

### Physical hardware

- Device:
- Test performed:
- Result:
- Validation level:

Use `Physically validated` only for actual observed hardware behavior.

Otherwise say `Pending physical validation`.

### Important evidence

List the most important concrete observations, test assertions, logs, or invariants that support the implementation.

### Remaining limitations / risks

State anything still unsupported or uncertain.

Examples:

- feature-state runtime polling intentionally deferred,
- trigger-only source cannot resynchronize after reconnect,
- hardware acceptance pending,
- a specific interface shape has not been physically tested.

### Recommended next bounded task

One specific next task only.

### Git discipline confirmation

Confirm:

- `main` untouched,
- no merge,
- no tag,
- no release,
- feature branch pushed,
- intentional prior commits retained.
