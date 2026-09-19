# OMUS motion-transparency validation

The production remapper can record exact physical and virtual `REL_X`/`REL_Y`
frames at its evdev-to-uinput boundary. The diagnostic is read-only with respect
to hardware and does not change DPI, polling, HID++, discovery, or write
authority. Configured button mappings and DPI controls continue through the
normal runtime path.

Stop the background service before each foreground run so only one process owns
the physical evdev node. Use the normal configuration and label each required
workload:

```bash
systemctl --user stop omus.service
omus run --motion-diagnostic motion-A.json --motion-workload A
omus run --motion-diagnostic motion-B.json --motion-workload B
omus run --motion-diagnostic motion-C.json --motion-workload C
systemctl --user start omus.service
```

End each run with `Ctrl+C` after exercising the workload:

- A: slow precise movement and small circles.
- B: fast continuous sweeps.
- C: aggressive movement while pressing/remapping buttons and changing DPI.

Each JSON report records physical and virtual motion frames, matched/dropped/
duplicated frames and events, modified axes, ordering/coalescing/framing
violations, effective physical and virtual frame rates, `SYN_DROPPED`, and
forwarding latency minimum/median/p95/p99/maximum with spike and batching
counts. `pass` is true only when enough motion frames were captured and all
loss, duplication, modification, ordering, coalescing, framing, and
`SYN_DROPPED` failure counters are zero. Latency is reported independently and
is never excluded to obtain PASS.

The measurement boundary is the instant a complete physical frame reaches
`MouseRemapper` through the instant its corresponding virtual frame is
submitted to uinput. This measures OMUS forwarding latency; it does not claim
to include downstream compositor/application scheduling latency.

## G305 sleep/wake soak

One diagnostic run may remain active across repeated genuine sleep cycles. A
wake after at least 30 seconds without input creates a `wake_cycles` record in
the JSON report. Each completed record keeps separate
`first_virtual_input_ms` and `full_omus_ready_ms` values; neither is substituted
for the other. The latency summaries logged at shutdown include
minimum/median/p95/p99/maximum.

Before the soak, confirm motion, configured remaps, DPI cycling and
notifications, and the configured 1000 Hz report rate. Then perform at least
ten natural hardware sleep/wake cycles without stopping OMUS or touching the
receiver. For each cycle retain the JSON timestamps and fill the operator-only
observations that software cannot infer:

| Cycle | Wake detected | Pointer | Mappings | DPI control | Notification | Service running | Manual intervention | First input | Full ready |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |  |  |  |
| 4 |  |  |  |  |  |  |  |  |  |
| 5 |  |  |  |  |  |  |  |  |  |
| 6 |  |  |  |  |  |  |  |  |  |
| 7 |  |  |  |  |  |  |  |  |  |
| 8 |  |  |  |  |  |  |  |  |  |
| 9 |  |  |  |  |  |  |  |  |  |
| 10 |  |  |  |  |  |  |  |  |  |

After ordinary wake succeeds, repeat with immediate rapid motion, ordinary and
remapped button presses, and DPI-cycle presses. Preserve the journal and JSON
report on any failure; do not restart the service before capturing the failed
state. The first physical event may be called lost by OMUS only if kernel evdev
evidence shows it reached the selected physical stream but is absent from the
virtual trace.
