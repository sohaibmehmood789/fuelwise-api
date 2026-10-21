"""Single-host, multi-process locks. Deployment must keep workers on one host."""
import fcntl
import hashlib
import time
from contextlib import contextmanager
from django.conf import settings
from .errors import PlanningError


@contextmanager
def lock(key, timeout=45):
    settings.LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = settings.LOCK_DIR / hashlib.sha256(key.encode()).hexdigest()
    with path.open('a+') as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise PlanningError('busy', 'Provider queue is busy; please retry.', 503)
                time.sleep(.05)
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def provider_slot(provider):
    # Hold the lock through the HTTP call, sharing a 1 request/sec ceiling.
    with lock('provider:' + provider) as handle:
        handle.seek(0)
        last = float(handle.read() or 0)
        time.sleep(max(0, 1.05 - (time.time() - last)))
        handle.seek(0)
        handle.truncate()
        handle.write(str(time.time()))
        handle.flush()
        yield
