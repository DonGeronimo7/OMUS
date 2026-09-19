# G305 motion and wake acceptance — 2026-09-19

## Evidence boundary

These results are operator-provided physical acceptance evidence from a
Logitech G305 Lightspeed on Fedora 44 running commit
`5a1997f852fc026553df6549e6154493994e77c1`. The four locally supplied JSON
reports were inspected directly. Their full frame streams are generated local
artifacts and are not committed; SHA-256 digests bind this summary to the files
that were reviewed.

The reports contain no device paths, serial numbers, usernames, or hostnames.
They do contain raw event and monotonic/wall-clock timestamps, so the concise
derived evidence below is the appropriate repository record.

## Motion transparency

| Workload | Frames | Motion events | Effective physical / virtual Hz | Latency ms min / median / p95 / p99 / max | Result |
|---|---:|---:|---:|---:|---|
| A — slow precision/circles | 24,423 | 33,943 | 206.064 / 206.065 | 0.010770 / 0.015900 / 0.034502 / 0.045589 / 0.536936 | PASS |
| B — sustained fast movement | 21,167 | 37,438 | 992.569 / 992.576 | 0.010630 / 0.015740 / 0.029306 / 0.037555 / 0.323852 | PASS |
| C — aggressive movement with DPI/notifications | 13,764 | 22,565 | 347.076 / 347.078 | 0.010079 / 0.016341 / 0.032692 / 0.043750 / 0.307953 | PASS |
| Ten-cycle wake run | 40,578 | 66,345 | 50.736 / 50.736 | 0.010460 / 0.015649 / 0.031930 / 0.042852 / 0.751022 | PASS |

Every report records equal physical/virtual frame and event counts, every frame
matched, and zero dropped/duplicated frames or events, modified `REL_X`/`REL_Y`,
ordering violations, unexpected coalescing, framing violations, `SYN_DROPPED`,
latency spikes, or batched frames.

Workload A also recorded one wake/input T0→T3 transition of `0.102614 ms`.

## Genuine sleep/wake soak

The dedicated run contains ten completed, operator-confirmed genuine hardware
wake trials. All used `evdev-input` as the first Linux-visible evidence. T0→T1
and T0→T2 were `0.000 ms` in every trial because input was recognized at T0 and
the already-ready management path required no later recovery.

| Cycle | T0→T3 first virtual input (ms) |
|---:|---:|
| 1 | 0.144854 |
| 2 | 0.086464 |
| 3 | 0.107484 |
| 4 | 0.134094 |
| 5 | 0.206691 |
| 6 | 0.168749 |
| 7 | 0.124235 |
| 8 | 0.093607 |
| 9 | 0.173579 |
| 10 | 0.101933 |

Summary: minimum `0.086 ms`, median `0.129 ms`, p95/p99/maximum `0.207 ms`.
Motion transparency remained PASS throughout. The operator also observed native
control-mode preservation for polling and successful reconciliation of 3000 DPI
through the Automatic Discovery Native HID adapter. No motion-transparency or
wake failure was reported.

## Reviewed artifact digests

```text
9c550d92dca1f7a0cf5ee24f2bc7692b1796f93c6d1f00c916000841fd46d099  motion-A.json
71fee1b37cded548cb431b6f545500defb89d6fec65a65893b413f4ed166c5f2  motion-B.json
9f81275f188ea9389fe71e2a70b2873786f98e6ece8b18ab1719d69344448328  motion-C.json
da92656eeb021d6f40c853820565c55515d16282b4d566935daf331627086b7b  motion-wake.json
```

Validation level: **Physically validated** for this Logitech G305 and these
motion/sleep-wake workloads. This evidence grants no authority or support claim
for another model.
