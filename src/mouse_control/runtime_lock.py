"""Kernel-owned runtime exclusion; stale files never imply a live process."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path


@contextmanager
def runtime_lock():
    directory = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    descriptor = os.open(directory / 'omus-runtime.lock',
                         os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('OMUS runtime is already running') from None
        yield
    finally:
        os.close(descriptor)
