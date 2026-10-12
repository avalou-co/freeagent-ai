"""DNS lifetime limits and TLS hostname verification over pinned public addresses."""

import http.client
import ipaddress
import socket
import ssl
import threading
from contextlib import contextmanager, suppress

import dns.exception
import dns.resolver


def resolve_public(host, deadline, resolver=None):
    resolver = resolver or dns.resolver.Resolver()
    addresses = []
    for family in ["A", "AAAA"]:
        try:
            answer = resolver.resolve(host, family, lifetime=deadline.remaining(), search=False)
            addresses.extend(str(record) for record in answer)
        except dns.resolver.NoAnswer:
            continue
        except dns.exception.DNSException:
            raise ValueError("DNS resolution failed within request deadline") from None
    if not addresses or any(
        not ipaddress.ip_address(address).is_global
        or ipaddress.ip_address(address).is_multicast
        or ipaddress.ip_address(address).is_reserved
        for address in addresses
    ):
        raise ValueError("Download/API address is not public")
    return list(dict.fromkeys(addresses))


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, addresses, deadline):
        super().__init__(host, timeout=deadline.remaining())
        self.addresses, self.deadline = addresses, deadline
        self.tls_context = ssl.create_default_context()

    def connect(self):
        for address in self.addresses:
            raw = None
            try:
                raw = socket.create_connection((address, 443), timeout=self.deadline.remaining())
                raw.settimeout(self.deadline.remaining())
                self.sock = self.tls_context.wrap_socket(raw, server_hostname=self.host)
                return
            except OSError:
                if raw is not None:
                    raw.close()
        raise OSError("TLS connection failed within request deadline") from None


def set_read_timeout(response, deadline):
    if response.fp is not None:
        # CPython HTTPResponse exposes its socket through BufferedReader.raw.
        sock = response.fp.raw._sock
        sock.settimeout(deadline.remaining())


@contextmanager
def socket_budget(sock, deadline):
    """Interrupt header parsing as well as body reads at the absolute end time.

    HTTPResponse internally reads multiple header lines; an idle socket timeout alone
    does not stop a slow-drip peer. Shutdown the captured socket even when http.client
    has transferred its ownership to a Connection:close response file.
    """

    def expire():
        with suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)

    timer = threading.Timer(deadline.remaining(), expire)
    timer.daemon = True
    timer.start()
    try:
        yield
        deadline.remaining()
    finally:
        timer.cancel()
        timer.join()
