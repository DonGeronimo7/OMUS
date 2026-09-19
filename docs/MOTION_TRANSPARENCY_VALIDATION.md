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
