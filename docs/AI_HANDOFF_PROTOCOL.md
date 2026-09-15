# ChatGPT ↔ Codex Handoff Protocol

This file is the persistent coordination contract for AI-assisted development of
Mouse Control. It exists so ChatGPT can act as project manager/reviewer while
Codex acts as the implementation engineer without relying on chat memory.

The protocol is intentionally stored in Git. Repository state is authoritative.
If chat context conflicts with committed code, tests, `AGENTS.md`, or
`docs/PROJECT_STATUS.md`, inspect the repository and call out the conflict.

## Roles

### ChatGPT — project manager / reviewer

ChatGPT should:

- inspect the current repository before planning significant work;
- turn user goals and hardware observations into bounded engineering tasks;
- preserve architectural intent and identify regressions or unsafe assumptions;
- review Codex commits/diffs and physical-test results;
- distinguish verified behavior from hypotheses;
- decide with the user what the next bounded task should be;
- avoid asking Codex to solve unrelated problems in the same task.

ChatGPT may make repository changes when the user explicitly asks it to, but
normal feature implementation should be handed to Codex so there is one clear
implementation owner at a time.

### Codex — implementation engineer

Codex should:

- read the repository coordination files before beginning work;
- inspect the actual current code rather than relying on the task prompt's
  description of repository state;
- implement the smallest complete change that satisfies the task;
- add or update tests alongside behavioral changes;
- preserve hardware safety and backend isolation rules;
- run the required validation before handoff;
- leave the repository in a state ChatGPT can inspect from Git;
- report unresolved questions rather than hiding them behind fallbacks or
  speculative behavior.

## Mandatory startup sequence for Codex

Before modifying code, read these files in this order:

1. `AGENTS.md`
2. `docs/AI_HANDOFF_PROTOCOL.md`
3. `docs/PROJECT_STATUS.md`
4. the most recent entry in `docs/AI_HANDOFF_LOG.md`, if the file exists
5. files directly relevant to the assigned task

Then inspect the current branch, working tree, and recent commits.

Do not assume a previous ChatGPT/Codex conversation describes HEAD accurately.

If the working tree contains unrelated user changes, preserve them. Do not
silently discard, overwrite, or fold them into the task.

## Task contract

A handoff task should contain as many of these fields as applicable:

- **Goal** — observable outcome the user wants.
- **Current evidence** — known code state, hardware observations, logs, or
  reproduction results.
- **Scope** — components that may be changed.
- **Do not change** — behavior or architecture that must remain intact.
- **Acceptance criteria** — tests and/or physical observations that prove the
  task is complete.
- **Safety constraints** — especially for HID writes and persistent hardware
  state.
- **Deliverable** — expected branch/commit/report.

Treat acceptance criteria as evidence requirements, not permission to fake or
mock a physical result. A hardware result is `physically validated` only when
it was actually observed on hardware and reported as such.

## Implementation rules

Follow `AGENTS.md` as the primary engineering policy. In addition:

- Prefer root-cause fixes over compatibility shims when the root cause can be
  established safely.
- Do not broaden a device-specific observation into a vendor-wide or generic
  claim without evidence.
- Do not make persistent/onboard hardware writes merely to make a test pass.
- Never report a successful hardware write solely because a command received a
  protocol acknowledgement. Where possible, read back canonical state or use a
  protocol-defined confirmation event.
- Preserve ordinary evdev/uinput remapping when optional hardware control fails.
- Keep diagnostics explicit enough that the next agent can distinguish
  discovery failure, transport failure, protocol rejection, mode restrictions,
  write failure, and readback mismatch.
- Avoid opportunistic refactors unrelated to the assigned task.

## Validation levels

Use these labels consistently in handoffs:

- **Code-reviewed** — implementation inspected, no execution claim.
- **Unit-tested** — deterministic automated tests pass.
- **Integration-tested** — relevant software components were exercised
  together without requiring the target physical device.
- **Physically validated** — behavior was observed on the named real device.
- **Unverified** — implementation or hypothesis still lacks the required
  evidence.

Never upgrade a validation level by inference.

For normal implementation work, run at minimum:

```text
python3 -m pytest -q
python3 -m compileall -q src tests
git diff --check
```

Also run task-specific tests and record the exact results.

## Git handoff rules

Git is the bridge between ChatGPT and Codex.

For a substantial task, prefer a bounded feature/fix branch unless the user has
explicitly directed work on another branch. Do not merge, tag, release, publish,
or push to `main` without explicit user authorization, as required by
`AGENTS.md`.

When work is ready for review:

1. ensure the diff contains only intended changes;
2. run validation;
3. commit the coherent implementation when the task permits committing;
4. push the working branch when the user has asked for a Git-visible handoff;
5. append a concise entry to `docs/AI_HANDOFF_LOG.md` when that file is part of
   the current workflow;
6. give the user the structured handoff report below.

A commit hash is the preferred review anchor. If work remains uncommitted, say
so explicitly and list the modified files.

## Required Codex → ChatGPT handoff report

End each implementation task with this structure:

```text
HANDOFF

Goal:

Repository state:
- Branch:
- Commit:
- Working tree:

Files changed:
-

Behavior changed:
-

Validation:
- Automated:
- Physical hardware:
- Validation level:

Evidence / important observations:
-

Risks or unresolved questions:
-

Recommended next bounded task:
-
```

Do not say `done`, `fixed`, `supported`, or `validated` more broadly than the
recorded evidence allows.

## ChatGPT review sequence

When the user brings a Codex handoff back to ChatGPT, ChatGPT should:

1. fetch recent commits/branch state from GitHub;
2. inspect the referenced commit and relevant changed files;
3. compare the implementation against the task acceptance criteria;
4. check that tests exercise the failure cases as well as the happy path;
5. separate code correctness from physical validation;
6. identify regressions, architecture drift, or unsafe hardware assumptions;
7. give the user a concise project-state update and the next recommended task.

ChatGPT should not treat Codex's prose report as proof when the repository can
be inspected directly.

## Persistent project status

`docs/PROJECT_STATUS.md` should describe the current architecture and validation
state, not a chronological diary. Update it when a completed task materially
changes architecture, supported behavior, or physical-validation status.

`docs/AI_HANDOFF_LOG.md` is the chronological coordination trail. Keep entries
short and technical so it does not become a second changelog.

## Protocol evolution

This protocol is expected to improve as the project matures.

Codex and ChatGPT may propose improvements when a handoff exposes ambiguity,
missing evidence, repeated work, unsafe assumptions, or coordination friction.
Protocol changes should be deliberate and committed separately from unrelated
feature code whenever practical.

Neither agent should silently weaken hardware safety rules, validation
requirements, or the user's control over merges/releases.
