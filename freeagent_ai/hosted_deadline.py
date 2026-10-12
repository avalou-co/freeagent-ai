"""One monotonic budget shared by DNS, TLS, database, retries and API requests."""

import time
from contextvars import ContextVar

deadline_context: ContextVar = ContextVar("hosted_deadline")


class Deadline:
    def __init__(self, seconds: float = 45):
        self.ends = time.monotonic() + seconds

    def remaining(self):
        value = self.ends - time.monotonic()
        if value <= 0:
            raise TimeoutError("Request deadline exceeded; inspect any submitted write")
        return value

    def sleep(self, seconds):
        if seconds >= self.remaining():
            raise TimeoutError("Rate limit wait exceeds request deadline; retry the read later")
        time.sleep(seconds)


def rpc_timeout():
    try:
        return min(5, deadline_context.get().remaining())
    except LookupError:
        return 5
