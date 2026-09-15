# Logitech G305 core hardware acceptance

Run this checklist on the USB Logitech G305 Lightspeed receiver
(`0003:046d:4074`) after installing the stabilization branch. These checks are
intentionally physical and are not claimed by the automated suite.

## Preparation

1. Back up `~/.config/mouse-control/config.toml`.
2. Run `mouse-control doctor` and confirm the selected mouse is the G305.
3. Run `mouse-control setup`, retain stages `800, 1500, 2000, 2500, 3000`,
   select a polling rate, enable DPI notifications, and retain at least one
   mouse-to-key or keyboard-chord mapping.
4. Start the service with `mouse-control restart`.
5. Follow service logs in a second terminal with
   `journalctl --user -u mouse-control.service -f`.

Do not use tools that write onboard profile sectors. Mouse Control should make
only live mode, report-rate, and adjustable-DPI changes.

## Polling transaction

Use `mouse-control setup` to apply each transition in order:

1. `1000 -> 500 Hz`
2. `500 -> 250 Hz`
3. `250 -> 125 Hz`
4. `125 -> 1000 Hz`

For every transition, confirm that setup reports a verified write, subsequent
hardware readback shows the requested value, pointer input remains responsive,
and no onboard profile, button binding, DPI table, lighting state, or other
persistent setting changes unexpectedly. Confirm the device remains in Host
mode after each successful transaction.

## DPI button and notifications

1. Begin at `800 DPI`.
2. Press the physical DPI button slowly and verify
   `1500 -> 2000 -> 2500 -> 3000 -> 800`.
3. For each press, confirm cursor sensitivity changes, hardware readback equals
   the popup value, and exactly one distinct popup appears.
4. Press rapidly through at least two full cycles. Confirm all ten requested
   transitions occur in order and all ten popups are visible/queued; none are
   coalesced.
5. Confirm a firmware/off-list `800` value never displaces the configured
   sequence. If starting from any off-list value, the next press must select
   the first configured stage.
6. Disable DPI notifications and confirm physical and software DPI cycling
   continue without popups. Re-enable notifications afterward.

## Combined Host-mode behavior

While the G305 is in Host mode, verify all of the following together:

- physical DPI-button cycling;
- mapped `dpi-cycle` action;
- normal pointer/button passthrough;
- disabled and mouse-to-mouse mappings;
- mouse-to-key mappings and keyboard chords, including correct release;
- battery/status tray updates;
- one notification per DPI transition.

## Reconnect and lifecycle

With the service running:

1. Turn the mouse off, wait several seconds, and turn it on.
2. Confirm remapping recovers without restarting the service.
3. Confirm configured polling and active DPI are restored by hardware readback.
4. Confirm physical and software DPI cycling, notifications, and battery status
   resume without duplicate monitors or duplicate popups.
5. Unplug the receiver, wait several seconds, and reinsert it.
6. Repeat the same remapping, polling, DPI, notification, and battery checks.
7. During a reconnect retry, run `mouse-control stop` and confirm shutdown is
   prompt and leaves no stuck virtual key/button output.

## Service lifecycle

Run each command and verify its reported state and behavior:

```text
mouse-control stop
mouse-control start
mouse-control restart
mouse-control status
```

After `restart`, confirm configured polling, active DPI, physical/software DPI
cycling, remapping, keyboard mappings, notifications, and battery reporting all
return. Review the journal for rollback failures, ambiguity refusals, reader
errors, or repeated reconnect loops before accepting the branch.
