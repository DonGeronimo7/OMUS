# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private session bus integration: never touches the user's desktop."""
import asyncio
import shutil
import subprocess

import pytest
from dbus_next import Message, BusType
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method

from mouse_control.battery import StatusNotifierTray
from mouse_control.hardware import BatteryState
from mouse_control.tray_session import ITEM, WATCHER


@pytest.mark.skipif(not shutil.which('dbus-daemon'), reason='private dbus-daemon unavailable')
def test_exported_item_survives_watcher_replacement_and_repeated_runtime_lifetimes(monkeypatch):
    daemon = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address'],
                              stdout=subprocess.PIPE, text=True)
    address = daemon.stdout.readline().strip()
    if not address:
        daemon.wait(timeout=5)
        daemon.stdout.close()
        pytest.skip('sandbox does not permit a private D-Bus socket')
    monkeypatch.setenv('DBUS_SESSION_BUS_ADDRESS', address)

    class Watcher(ServiceInterface):
        def __init__(self):
            super().__init__(WATCHER)
            self.items = []
        @method()
        def RegisterStatusNotifierItem(self, name: 's') -> '':  # noqa: F722, F821 — D-Bus signatures
            self.items.append(name)

    async def wait_for(predicate):
        for _ in range(200):
            if predicate(): return
            await asyncio.sleep(.01)
        assert predicate()

    async def scenario():
        host = await MessageBus(bus_type=BusType.SESSION).connect()
        try:
            for _ in range(3):
                tray = StatusNotifierTray()
                try:
                    tray.update(BatteryState(percentage=None, status='unknown'), 'test mouse')
                    watcher = Watcher()
                    host.export('/StatusNotifierWatcher', watcher)
                    await host.request_name(WATCHER)
                    await wait_for(lambda: watcher.items)
                    assert watcher.items == [ITEM]
                    tray.update(BatteryState(percentage=83), 'test mouse')
                    await asyncio.sleep(.03)
                    reply = await host.call(Message(destination=ITEM, path='/StatusNotifierItem',
                        interface='org.freedesktop.DBus.Properties', member='Get', signature='ss',
                        body=['org.kde.StatusNotifierItem', 'XAyatanaLabel']))
                    assert reply.body[0].value == '83%'
                    await host.release_name(WATCHER)
                    await asyncio.sleep(.02)
                    host.unexport('/StatusNotifierWatcher')
                    watcher = Watcher()
                    host.export('/StatusNotifierWatcher', watcher)
                    await host.request_name(WATCHER)
                    await wait_for(lambda: watcher.items)
                    assert watcher.items == [ITEM]
                finally:
                    tray.close()
                assert not tray._thread.is_alive()
                await host.release_name(WATCHER)
                host.unexport('/StatusNotifierWatcher')
        finally:
            host.disconnect()
    try:
        asyncio.run(scenario())
    finally:
        daemon.terminate()
        daemon.wait(timeout=5)
        daemon.stdout.close()
