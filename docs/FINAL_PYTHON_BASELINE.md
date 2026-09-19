# Canonical final Python behavioral baseline

The canonical OMUS Python behavioral baseline is release tag `v1.0.1` and the
exact Git commit to which that annotated tag resolves.

The baseline contract is defined by:

- `docs/FINAL_PYTHON_STABILITY_AUDIT.md`;
- `docs/PRE_RUST_QUALITY_AUDIT.md`;
- the complete deterministic test suite at the tagged commit; and
- the exact-device Logitech G305 physical evidence recorded for the accepted
  motion, wake, DPI, polling, reconnect, notification, battery, mapping, and
  service paths.

A future Rust implementation must preserve or improve this behavior and pass
the documented deterministic and physical acceptance gates. The Rust migration
is not part of v1.0.1 and has not begun.
