# Mouse Control v0.7.10

## Persistent battery tray

The battery tray now remains visible through transient HID++ battery read
timeouts, retaining the last known percentage. It hides only after three
consecutive failed reads, and a successful read resets the failure count.

The tray menu now shows only the battery percentage and, when available, the
battery status; it no longer repeats the mouse/device name.

## Terminal branding refresh

The terminal launcher branding and logo have been refreshed.
