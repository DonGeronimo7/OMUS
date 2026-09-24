# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exercise real exported SNI interfaces against controllable bus lifetimes."""
import asyncio
from types import SimpleNamespace

from dbus_next import Message
from dbus_next.constants import MessageType, RequestNameReply

from mouse_control.tray_session import TraySession, WATCHER, DBUS


class Bus:
    def __init__(self, owner=""):
        self.owner = owner
        self.handlers = []
        self.registrations = []
        self.exports = {}
        self.fail_registration = False
        self.disconnected = asyncio.Event()
    async def connect(self): return self
    def export(self, path, service): self.exports[path] = service
    def unexport(self, path): self.exports.pop(path, None)
    async def request_name(self, *args): return RequestNameReply.PRIMARY_OWNER
    def add_message_handler(self, handler): self.handlers.append(handler)
    def remove_message_handler(self, handler): self.handlers.remove(handler)
    async def call(self, message):
        if message.member == "GetNameOwner":
            return SimpleNamespace(message_type=MessageType.METHOD_RETURN if self.owner else MessageType.ERROR,
                                   body=[self.owner])
        if message.member == "RegisterStatusNotifierItem":
            if self.fail_registration:
                self.fail_registration = False
                return SimpleNamespace(message_type=MessageType.ERROR, error_name="temporary")
            self.registrations.append(message.destination)
        return SimpleNamespace(message_type=MessageType.METHOD_RETURN)
    async def wait_for_disconnect(self): await self.disconnected.wait()
    def disconnect(self): self.disconnected.set()
    def change(self, owner):
        old, self.owner = self.owner, owner
        message = Message.new_signal('/org/freedesktop/DBus', DBUS, 'NameOwnerChanged', 'sss',
                                     [WATCHER, old, owner])
        message.sender = DBUS
        for handler in self.handlers: handler(message)


async def until(predicate):
    for _ in range(300):
        if predicate(): return
        await asyncio.sleep(.001)
    assert predicate()


def test_late_watcher_restart_and_shutdown_have_one_registration_per_owner():
    async def scenario():
        bus = Bus()
        task = asyncio.create_task(TraySession(lambda: bus, .001, .01).run(object(), object(), '/menu'))
        await until(lambda: bus.handlers)
        await asyncio.sleep(.01)
        assert not bus.registrations
        bus.change(':1.10')
        await until(lambda: len(bus.registrations) == 1)
        bus.change(':1.10')
        await asyncio.sleep(.01)
        assert bus.registrations == [':1.10']
        bus.change('')
        await asyncio.sleep(.01)
        bus.change(':1.11')
        await until(lambda: len(bus.registrations) == 2)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert not bus.handlers and not bus.exports
        bus.change(':1.12')
        assert bus.registrations == [':1.10', ':1.11']
    asyncio.run(scenario())


def test_bus_disconnect_reconstructs_exports_and_registration_without_battery_update():
    async def scenario():
        first, second = Bus(':1.10'), Bus(':1.20')
        buses = iter([first, second])
        service, menu = object(), object()
        task = asyncio.create_task(TraySession(lambda: next(buses), .001, .01).run(service, menu, '/menu'))
        await until(lambda: first.registrations)
        first.disconnect()
        await until(lambda: second.registrations)
        assert second.exports['/StatusNotifierItem'] is service
        assert not first.handlers and not first.exports
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert not second.handlers and not second.exports
    asyncio.run(scenario())


def test_initial_bus_failure_and_error_reply_retry_without_new_battery_sample():
    async def scenario():
        bus = Bus(':1.10')
        bus.fail_registration = True
        attempts = []
        def factory():
            attempts.append(1)
            if len(attempts) == 1: raise OSError('bus absent')
            return bus
        task = asyncio.create_task(TraySession(factory, .001, .01).run(object(), object(), '/menu'))
        await until(lambda: bus.registrations)
        assert len(attempts) == 2 and bus.registrations == [':1.10']
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_watcher_release_and_reacquire_in_same_dispatch_turn_registers_again():
    async def scenario():
        bus = Bus(':1.10')
        task = asyncio.create_task(TraySession(lambda: bus, .001, .01).run(object(), object(), '/menu'))
        await until(lambda: bus.registrations)
        bus.change('')
        bus.change(':1.10')
        await until(lambda: len(bus.registrations) == 2)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert bus.registrations == [':1.10', ':1.10']
    asyncio.run(scenario())
