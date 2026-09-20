"""Optional battery polling and an intentionally tiny StatusNotifier item."""
from __future__ import annotations

import asyncio
import logging
import threading

from .async_wake_queue import AsyncWakeQueue
from .hardware import BatteryState, HardwareBackend

LOG = logging.getLogger(__name__)
SNI_MENU_PATH = "/StatusNotifierMenu"

# Sampled from assets/omus-icon.png and fixed here so tray rendering never
# depends on a runtime image file.  IconPixmap is ARGB32 in network byte order,
# so each pixel below is serialized as alpha, red, green, blue.
_OMUS_VIOLET = (96, 15, 176)
_OMUS_PURPLE = (178, 68, 250)
_OMUS_LAVENDER = (213, 115, 255)
_OMUS_LOW_OUTLINE = (229, 164, 255)


def battery_icon(percentage: int) -> str:
    if percentage <= 10:
        return "battery-caution-symbolic"
    if percentage <= 25:
        return "battery-low-symbolic"
    if percentage <= 50:
        return "battery-medium-symbolic"
    if percentage <= 75:
        return "battery-good-symbolic"
    return "battery-full-symbolic"


def battery_pixmap(percentage: int, height: int) -> list[int | bytes]:
    """Return a crisp, rounded OMUS-purple SNI ARGB32 battery pixmap."""
    if not 0 <= percentage <= 100 or height < 16:
        raise ValueError("invalid battery pixmap dimensions or percentage")
    width = height
    margin = 1 if height < 28 else 2
    nub_width = max(2, round(height * .12))
    bx = margin
    bw = width - 2 * margin - nub_width
    bh = max(10, round(height * .58))
    by = (height - bh) // 2
    radius = max(3, round(height * .16))
    inset = 1 if height <= 22 else 2
    pixels = bytearray(width * height * 4)

    def dot(x: int, y: int, color: tuple[int, int, int] | None) -> None:
        if 0 <= x < width and 0 <= y < height:
            offset = (y * width + x) * 4
            pixels[offset:offset + 4] = (b"\0\0\0\0" if color is None else
                                          bytes((255, *color)))

    def rounded_rect(x: int, y: int, w: int, h: int, r: int,
                     color_at) -> None:
        """Rasterize a pixel-aligned rounded rectangle without fuzzy edges."""
        r = max(0, min(r, w // 2, h // 2))
        for row in range(y, y + h):
            for col in range(x, x + w):
                dx = max(x + r - col - .5, col + .5 - (x + w - r), 0)
                dy = max(y + r - row - .5, row + .5 - (y + h - r), 0)
                if dx * dx + dy * dy <= r * r:
                    dot(col, row, color_at(col, row))

    outline = _OMUS_LOW_OUTLINE if percentage <= 10 else _OMUS_LAVENDER
    solid_outline = lambda _x, _y: outline

    # The terminal is drawn first so its softly rounded left edge tucks neatly
    # behind the body instead of reading as a separate rectangular block.
    terminal_height = max(3, bh // 3)
    terminal_y = by + (bh - terminal_height) // 2
    rounded_rect(bx + bw - 1, terminal_y, nub_width + 1, terminal_height,
                 max(1, nub_width // 2), solid_outline)
    rounded_rect(bx, by, bw, bh, radius, solid_outline)

    ix, iy = bx + inset, by + inset
    iw, ih = bw - 2 * inset, bh - 2 * inset
    inner_radius = max(1, radius - inset)
    rounded_rect(ix, iy, iw, ih, inner_radius, lambda _x, _y: None)

    fill_width = round(iw * percentage / 100)
    if fill_width:
        def gradient(col: int, _row: int) -> tuple[int, int, int] | None:
            if col >= ix + fill_width:
                return None
            position = 0 if fill_width == 1 else (col - ix) / (fill_width - 1)
            # The mid-purple anchor keeps short, low-resolution ramps vivid.
            start, end = (_OMUS_VIOLET, _OMUS_PURPLE) if position < .6 else (
                _OMUS_PURPLE, _OMUS_LAVENDER)
            local = position / .6 if position < .6 else (position - .6) / .4
            return tuple(round(a + (b - a) * local) for a, b in zip(start, end))

        rounded_rect(ix, iy, iw, ih, inner_radius, gradient)
    # dbus-next represents D-Bus STRUCT values as lists, while the `ay`
    # member specifically requires immutable bytes.
    return [width, height, bytes(pixels)]


def battery_tooltip(device_name: str, state: BatteryState) -> list[object]:
    """Return the SNI ToolTip ``(sa(iiay)ss)`` value for one battery state."""
    if state.percentage is None:
        raise ValueError("battery percentage is required for a tooltip")
    description = f"Battery: {state.percentage}%"
    if state.status:
        description += f"\nStatus: {state.status.capitalize()}"
    # A D-Bus STRUCT is represented by a list in dbus-next.  The empty icon
    # pixmap array leaves the already-published IconPixmap as the glyph source.
    return ["", [], device_name, description]


def battery_menu_properties(device_name: str, state: BatteryState):
    """Return DBusMenu properties for the live, read-only battery rows.

    Values deliberately remain ``Variant`` instances: DBusMenu's property map
    is ``a{sv}``, unlike StatusNotifierItem's ordinary typed properties.
    """
    from dbus_next import Variant

    if state.percentage is None:
        raise ValueError("battery percentage is required for a menu")
    rows = {
        1: {"label": Variant("s", f"Battery: {state.percentage}%"),
            "enabled": Variant("b", False)},
    }
    if state.status:
        rows[2] = {"label": Variant("s", f"Status: {state.status.capitalize()}"),
                   "enabled": Variant("b", False)}
    return rows


def battery_menu_layout(device_name: str, state: BatteryState) -> list[object]:
    """Return the DBusMenu root layout, using dbus-next struct/list shapes."""
    from dbus_next import Variant

    properties = battery_menu_properties(device_name, state)
    children = [Variant("(ia{sv}av)", [item_id, values, []])
                for item_id, values in properties.items()]
    return [0, {}, children]


class StatusNotifierTray:
    """One SNI item with a battery glyph, tooltip, and read-only DBusMenu."""


    def __init__(self) -> None:
        self.visible_percentage: int | None = None
        self._queue: AsyncWakeQueue[tuple[str, BatteryState] | None] = AsyncWakeQueue()
        self._thread: threading.Thread | None = None

    def update(self, state: BatteryState, device_name: str) -> None:
        if state.percentage is None or not 0 <= state.percentage <= 100:
            raise ValueError("battery percentage must be 0..100")
        self.visible_percentage = state.percentage
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=lambda: asyncio.run(self._run()),
                                            name="battery-tray", daemon=True)
            self._thread.start()
        self._queue.put((device_name, state))

    async def _run(self) -> None:
        bus = service = None
        try:
            from dbus_next import BusType, Variant
            from dbus_next.aio import MessageBus
            from dbus_next.service import ServiceInterface, dbus_property, method, signal
            from dbus_next.constants import PropertyAccess

            class Item(ServiceInterface):
                def __init__(self, device_name, initial_state):
                    super().__init__("org.kde.StatusNotifierItem")
                    self.device_name = device_name
                    self.state = initial_state
                @dbus_property(access=PropertyAccess.READ)
                def Category(self) -> "s": return "Hardware"
                @dbus_property(access=PropertyAccess.READ)
                def Id(self) -> "s": return "omus-battery"
                @dbus_property(access=PropertyAccess.READ)
                def Title(self) -> "s": return self.device_name
                @dbus_property(access=PropertyAccess.READ)
                def Status(self) -> "s": return "Active"
                @dbus_property(access=PropertyAccess.READ)
                def IconName(self) -> "s": return ""
                @dbus_property(access=PropertyAccess.READ)
                def IconPixmap(self) -> "a(iiay)":
                    return [battery_pixmap(self.state.percentage, size) for size in (16, 20, 22, 24, 32)]
                @dbus_property(access=PropertyAccess.READ)
                def ToolTip(self) -> "(sa(iiay)ss)":
                    return battery_tooltip(self.device_name, self.state)
                @dbus_property(access=PropertyAccess.READ)
                def Menu(self) -> "o": return SNI_MENU_PATH
                @dbus_property(access=PropertyAccess.READ)
                def XAyatanaLabel(self) -> "s": return f"{self.state.percentage}%"
                @dbus_property(access=PropertyAccess.READ)
                def XAyatanaLabelGuide(self) -> "s": return "100%"
                @signal()
                def NewIcon(self) -> "": return None
                def set_state(self, device_name, state, menu):
                    self.device_name = device_name
                    self.state = state
                    self.emit_properties_changed({"Title": self.Title, "IconPixmap": self.IconPixmap,
                                                  "ToolTip": self.ToolTip,
                                                  "XAyatanaLabel": self.XAyatanaLabel})
                    self.NewIcon()
                    menu.set_state(device_name, state)

            class Menu(ServiceInterface):
                """The standard com.canonical.dbusmenu surface for tray hosts."""
                def __init__(self, device_name, initial_state):
                    super().__init__("com.canonical.dbusmenu")
                    self.device_name = device_name
                    self.state = initial_state
                    self.revision = 1

                @method()
                def GetLayout(self, parent_id: "i", recursion_depth: "i",
                              property_names: "as") -> "u(ia{sv}av)":
                    # This deliberately exposes only the root: every child is a
                    # disabled leaf, so recursion depth cannot add more content.
                    if parent_id != 0:
                        return [self.revision, [parent_id, {}, []]]
                    return [self.revision, battery_menu_layout(self.device_name, self.state)]

                @method()
                def GetGroupProperties(self, ids: "ai", property_names: "as") -> "a(ia{sv})":
                    properties = battery_menu_properties(self.device_name, self.state)
                    return [[item_id, properties[item_id]] for item_id in ids if item_id in properties]

                @method()
                def GetProperty(self, item_id: "i", name: "s") -> "v":
                    properties = battery_menu_properties(self.device_name, self.state)
                    return properties.get(item_id, {}).get(name, Variant("s", ""))

                @method()
                def Event(self, item_id: "i", event_id: "s", data: "v", timestamp: "u") -> "":
                    # All items are display-only; acknowledging events keeps the
                    # standard interface complete without adding tray actions.
                    return None

                @method()
                def AboutToShow(self, item_id: "i") -> "b":
                    return False

                @signal()
                def LayoutUpdated(self, revision: "u", parent: "i") -> "ui":
                    return [revision, parent]

                @signal()
                def ItemsPropertiesUpdated(self, updated: "a(ia{sv})",
                                           removed: "a(ias)") -> "a(ia{sv})a(ias)":
                    return [updated, removed]

                def set_state(self, device_name, state):
                    old_properties = battery_menu_properties(self.device_name, self.state)
                    self.device_name, self.state = device_name, state
                    new_properties = battery_menu_properties(device_name, state)
                    self.revision += 1
                    updated = [[item_id, properties] for item_id, properties in new_properties.items()
                               if old_properties.get(item_id) != properties]
                    removed = [[item_id, list(properties)] for item_id, properties in old_properties.items()
                               if item_id not in new_properties]
                    self.ItemsPropertiesUpdated(updated, removed)
                    self.LayoutUpdated(self.revision, 0)
            initial = await self._queue.get()
            self._queue.task_done()
            if initial is None:
                return
            initial_device_name, initial_state = initial
            bus = await MessageBus(bus_type=BusType.SESSION).connect()
            service = Item(initial_device_name, initial_state)
            menu = Menu(initial_device_name, initial_state)
            bus.export("/StatusNotifierItem", service)
            bus.export(SNI_MENU_PATH, menu)
            await bus.request_name("org.kde.StatusNotifierItem-omus")
            # Registering is best effort: a missing watcher must not kill remapping.
            try:
                from dbus_next import Message
                await bus.call(Message(destination="org.kde.StatusNotifierWatcher", path="/StatusNotifierWatcher",
                    interface="org.kde.StatusNotifierWatcher", member="RegisterStatusNotifierItem",
                    signature="s", body=["org.kde.StatusNotifierItem-omus"]))
            except Exception as exc:
                LOG.info("Battery tray watcher unavailable: %s", exc)
            while True:
                value = await self._queue.get()
                try:
                    if value is None: return
                    device_name, state = value
                    service.set_state(device_name, state, menu)
                finally:
                    self._queue.task_done()
        except Exception as exc:
            LOG.warning("Battery tray unavailable: %s", exc)
        finally:
            if bus:
                try: bus.disconnect()
                except Exception: pass

    def close(self) -> None:
        self.visible_percentage = None
        if self._thread and self._thread.is_alive():
            self._queue.put(None)
            self._thread.join(timeout=1)
        self._queue.close()
        # A temporarily unavailable battery removes the tray and may later
        # recover.  Leave the object restartable with a fresh queue.
        self._queue = AsyncWakeQueue()
        self._thread = None


class BatteryMonitorSupervisor:
    """Slow battery polling through the shared hardware lifecycle owner."""
    def __init__(self, backend: HardwareBackend, device, backend_factory, shutdown_event,
                 tray=None, interval: float = 60., retry_interval: float = 1.,
                 wake_coordinator=None) -> None:
        self.backend, self.device, self.backend_factory = backend, device, backend_factory
        self.shutdown_event, self.tray = shutdown_event, tray or StatusNotifierTray()
        self.interval, self.retry_interval, self._thread = interval, retry_interval, None
        self._consecutive_failures = 0
        self.wake_coordinator = wake_coordinator

    def _run(self) -> None:
        backend = self.backend
        shown = False
        while not self.shutdown_event.is_set():
            wake_generation = (self.wake_coordinator.generation
                               if self.wake_coordinator is not None else None)
            generation = getattr(backend, "generation", None)
            try:
                if not backend.supports_battery(self.device):
                    if not getattr(backend, "discovery_pending", True):
                        self._consecutive_failures = 0
                        if self.wake_coordinator is None:
                            stopped = self.shutdown_event.wait(self.interval)
                        else:
                            self.wake_coordinator.wait(
                                wake_generation, self.interval, self.shutdown_event)
                            stopped = (self.shutdown_event.is_set()
                                       or self.wake_coordinator.stopping)
                        if stopped:
                            break
                        continue
                    raise RuntimeError("battery unavailable")
                state = backend.get_battery_state(self.device)
                if state is None or state.percentage is None:
                    raise RuntimeError("battery percentage unavailable")
                LOG.debug("BatteryState delivered to monitor: %s; tray percentage: %s",
                          state, state.percentage)
                self.tray.update(state, self.device.name); shown = True
                self._consecutive_failures = 0
                if self.wake_coordinator is None:
                    stopped = self.shutdown_event.wait(self.interval)
                else:
                    self.wake_coordinator.wait(
                        wake_generation, self.interval, self.shutdown_event)
                    stopped = (self.shutdown_event.is_set()
                               or self.wake_coordinator.stopping)
                if stopped: break
                continue
            except Exception as exc:
                self._consecutive_failures += 1
                if shown and self._consecutive_failures >= 3:
                    LOG.info("Battery state unavailable after %d consecutive failures; removing tray item: %s",
                             self._consecutive_failures, exc)
                    self.tray.close(); shown = False
                elif not self.shutdown_event.is_set():
                    LOG.debug("Battery monitoring unavailable (failure %d/%d): %s",
                              self._consecutive_failures, 3, exc)
            if self.wake_coordinator is not None:
                self.wake_coordinator.wait(
                    wake_generation, self.retry_interval, self.shutdown_event)
                stopped = (self.shutdown_event.is_set()
                           or self.wake_coordinator.stopping)
            else:
                stopped = self.shutdown_event.wait(self.retry_interval)
            if stopped: break
            try:
                rebind = getattr(type(backend), "rebind", None)
                if callable(rebind):
                    rebind(backend, generation)
                else:
                    close = getattr(backend, "close", None)
                    if close: close()
                    backend = self.backend_factory(self.device)
            except Exception as exc:
                LOG.debug("Battery backend rediscovery unavailable: %s", exc)
        self.tray.close()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="battery-monitor", daemon=True)
        self._thread.start()
    def stop(self) -> None:
        self.shutdown_event.set()
        if self.wake_coordinator is not None: self.wake_coordinator.stop()
        if self._thread: self._thread.join(timeout=max(1., self.retry_interval + .5))
        self.tray.close()
