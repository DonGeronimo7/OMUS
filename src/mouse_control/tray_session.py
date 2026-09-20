"""Recover one exported tray item across watcher and session-bus lifetimes."""
from __future__ import annotations

import asyncio
import logging

from dbus_next import BusType, Message
from dbus_next.aio import MessageBus
from dbus_next.constants import MessageType, NameFlag, RequestNameReply

LOG = logging.getLogger(__name__)
WATCHER = "org.kde.StatusNotifierWatcher"
ITEM = "org.kde.StatusNotifierItem-omus"
DBUS = "org.freedesktop.DBus"


async def checked_call(bus, message):
    reply = await asyncio.wait_for(bus.call(message), 5)
    if reply is None or reply.message_type == MessageType.ERROR:
        raise RuntimeError(reply.error_name if reply else "D-Bus disconnected")
    return reply


class TraySession:
    """One connection owner; all child tasks are cancelled before reconnect."""
    def __init__(self, factory=None, retry_initial=1., retry_max=30.):
        self.factory = factory or (lambda: MessageBus(bus_type=BusType.SESSION))
        self.retry_initial, self.retry_max = retry_initial, retry_max

    async def _watch(self, bus):
        changed = asyncio.Event()
        owner = ""
        revision = 0

        def message_received(message):
            nonlocal owner, revision
            if (message.message_type == MessageType.SIGNAL and
                    message.interface == DBUS and message.member == "NameOwnerChanged" and
                    message.path == "/org/freedesktop/DBus" and
                    message.sender == DBUS and len(message.body) == 3 and
                    message.body[0] == WATCHER and message.body[1] != message.body[2]):
                owner = message.body[2]
                revision += 1
                LOG.info("StatusNotifier watcher %s", "discovered" if owner else "lost")
                changed.set()

        bus.add_message_handler(message_received)
        try:
            await checked_call(bus, Message(destination=DBUS, path="/org/freedesktop/DBus",
                interface=DBUS, member="AddMatch", signature="s",
                body=["type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='" + WATCHER + "'"]))
            initial_revision = revision
            reply = await asyncio.wait_for(bus.call(Message(destination=DBUS, path="/org/freedesktop/DBus",
                interface=DBUS, member="GetNameOwner", signature="s", body=[WATCHER])), 5)
            if revision == initial_revision and reply.message_type != MessageType.ERROR:
                owner = reply.body[0]
            if not owner:
                LOG.info("StatusNotifier watcher unavailable; waiting for owner")
            registered = None
            delay = self.retry_initial
            while True:
                changed.clear()
                target, epoch = owner, revision
                if target and (target, epoch) != registered:
                    try:
                        # Address the unique owner so an old reply cannot register
                        # the replacement watcher by accident.
                        await checked_call(bus, Message(destination=target, path="/StatusNotifierWatcher",
                            interface=WATCHER, member="RegisterStatusNotifierItem",
                            signature="s", body=[ITEM]))
                        registered = (target, epoch)
                        delay = self.retry_initial
                        LOG.info("Battery tray registered with watcher %s", target)
                    except Exception as exc:
                        LOG.debug("Tray registration retry: %s", exc)
                        try:
                            await asyncio.wait_for(changed.wait(), delay)
                        except asyncio.TimeoutError:
                            pass
                        delay = min(self.retry_max, delay * 2)
                        continue
                if not target:
                    registered = None
                if owner != target or revision != epoch:
                    continue
                await changed.wait()
        finally:
            bus.remove_message_handler(message_received)

    async def run(self, service, menu, menu_path):
        delay = self.retry_initial
        unavailable = False
        while True:
            bus = None
            tasks = []
            try:
                bus = self.factory()
                await asyncio.wait_for(bus.connect(), 5)
                bus.export("/StatusNotifierItem", service)
                bus.export(menu_path, menu)
                result = await asyncio.wait_for(bus.request_name(ITEM, NameFlag.DO_NOT_QUEUE), 5)
                if result != RequestNameReply.PRIMARY_OWNER:
                    raise RuntimeError("OMUS tray name already owned")
                delay = self.retry_initial
                unavailable = False
                tasks = [asyncio.create_task(self._watch(bus)),
                         asyncio.create_task(bus.wait_for_disconnect())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                raise ConnectionError("session bus disconnected")
            except Exception as exc:
                if not unavailable:
                    LOG.warning("Battery tray waiting for session bus: %s", exc)
                    unavailable = True
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if bus is not None:
                    bus.unexport("/StatusNotifierItem")
                    bus.unexport(menu_path)
                    bus.disconnect()
            await asyncio.sleep(delay)
            delay = min(self.retry_max, delay * 2)
