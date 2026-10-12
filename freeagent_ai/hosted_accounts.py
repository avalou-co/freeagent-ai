"""Encrypted account links, atomic replacement and generation-bound credential refresh.

Firestore is server-only. No API payloads, receipt contents or operator credentials are stored.
The revocation tombstone survives disconnect; each request keeps its original company context.
"""

import base64
import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .hosted_deadline import rpc_timeout


class AccessDenied(ValueError):
    """Safe public error; never include a credential, token or callback URL."""


class Store(Protocol):
    def get(self, collection: str, key: str) -> dict: ...
    def mutate(self, collection: str, key: str, change: Any) -> dict: ...


class MemoryStore:
    """Atomic test adapter, never selected by the deployed application."""

    def __init__(self):
        self.records: dict = {}
        self.lock = threading.RLock()

    def get(self, collection, key):
        with self.lock:
            return dict(self.records.get((collection, key), {}))

    def mutate(self, collection, key, change):
        with self.lock:
            record = change(self.get(collection, key))
            self.records[collection, key] = dict(record)
            return dict(record)


class FirestoreStore:
    def __init__(self, project):
        from google.cloud import firestore

        class DeadlineRPC:
            def __init__(self, api):
                self.api = api

            def __getattr__(self, name):
                method = getattr(self.api, name)

                def bounded(*args, **kwargs):
                    kwargs.update(timeout=rpc_timeout(), retry=None)
                    return method(*args, **kwargs)

                return bounded

        class DeadlineClient(firestore.Client):
            @property
            def _firestore_api(self):
                # Per-client wrapper also bounds SDK begin/commit/rollback transaction RPCs.
                return DeadlineRPC(super()._firestore_api)

        self.db = DeadlineClient(project=project)

    def get(self, collection, key):
        return self.db.collection(collection).document(key).get(timeout=rpc_timeout(), retry=None).to_dict() or {}

    def mutate(self, collection, key, change):
        from google.cloud import firestore

        ref = self.db.collection(collection).document(key)

        @firestore.transactional
        def commit(transaction):
            old = ref.get(transaction=transaction, timeout=rpc_timeout(), retry=None).to_dict() or {}
            record = change(old)
            if record.get("generation") != old.get("generation") and collection == "account_links":
                # A server commit timestamp closes the authentication-during-replacement race.
                record["revoked_before"] = firestore.SERVER_TIMESTAMP
            transaction.set(ref, record)

        commit(self.db.transaction(max_attempts=3))
        return self.get(collection, key)


def key_for(subject):
    return hashlib.sha256(subject.encode()).hexdigest()


def cutoff(record):
    value = record.get("revoked_before", 0)
    return value.timestamp() if isinstance(value, datetime) else float(value)


class TokenCipher:
    def __init__(self, keys: dict[str, str], active: str):
        self.keys = {version: AESGCM(base64.b64decode(value, validate=True)) for version, value in keys.items()}
        if active not in self.keys:
            raise ValueError("Active encryption key version missing")
        self.active = active

    def seal(self, value, binding):
        nonce = secrets.token_bytes(12)
        encrypted = self.keys[self.active].encrypt(nonce, json.dumps(value).encode(), binding.encode())
        return {"key_version": self.active, "ciphertext": base64.b64encode(nonce + encrypted).decode()}

    def open(self, envelope, binding):
        try:
            blob = base64.b64decode(envelope["ciphertext"], validate=True)
            return json.loads(self.keys[envelope["key_version"]].decrypt(blob[:12], blob[12:], binding.encode()))
        except Exception:
            raise AccessDenied("Account credentials unavailable; reconnect the account") from None


@dataclass(frozen=True)
class Principal:
    subject: str
    scopes: frozenset[str]
    primary_auth_time: float


@dataclass(frozen=True)
class Binding:
    subject: str
    company: str
    environment: str
    generation: int
    primary_auth_time: float

    @property
    def aad(self):
        return json.dumps([self.subject, self.company, self.environment, self.generation], separators=(",", ":"))


class Accounts:
    def __init__(self, store: Store, cipher: TokenCipher, clock=time.time):
        self.store, self.cipher, self.clock = store, cipher, clock

    def replace(self, subject, company, environment, tokens, expected_generation):
        if environment not in {"production", "sandbox"}:
            raise ValueError("Unknown FreeAgent environment")

        def change(old):
            if old.get("generation", 0) != expected_generation:
                raise AccessDenied("Account changed during linking; start again")
            generation = expected_generation + 1
            binding = Binding(subject, company, environment, generation, 0)
            return {
                "generation": generation,
                "company": company,
                "environment": environment,
                "active": True,
                "revoked_before": self.clock(),
                "tokens": self.cipher.seal(tokens, binding.aad),
            }

        return self.store.mutate("account_links", key_for(subject), change)

    def disconnect(self, subject, expected_generation):
        def change(old):
            if old.get("generation", 0) != expected_generation:
                raise AccessDenied("Account changed; reload before disconnecting")
            return {"generation": expected_generation + 1, "active": False, "revoked_before": self.clock()}

        return self.store.mutate("account_links", key_for(subject), change)

    def bind(self, principal):
        record = self.store.get("account_links", key_for(principal.subject))
        if not record.get("active") or principal.primary_auth_time <= cutoff(record):
            raise AccessDenied("Link your account, then sign in again and reconnect ChatGPT")
        return Binding(
            principal.subject,
            record["company"],
            record["environment"],
            record["generation"],
            principal.primary_auth_time,
        )

    def check(self, binding):
        record = self.store.get("account_links", key_for(binding.subject))
        if (
            not record.get("active")
            or record.get("generation") != binding.generation
            or record.get("company") != binding.company
            or record.get("environment") != binding.environment
            or binding.primary_auth_time <= cutoff(record)
        ):
            raise AccessDenied("Account authorization changed; reconnect ChatGPT")
        return record

    def credentials(self, binding):
        return self.cipher.open(self.check(binding)["tokens"], binding.aad)

    def refresh(self, binding, exchange):
        lease = secrets.token_urlsafe(24)
        self.check(binding)

        def acquire(old):
            if old.get("generation") != binding.generation or not old.get("active"):
                raise AccessDenied("Account authorization changed")
            if old.get("refresh_until", 0) > self.clock():
                raise AccessDenied("Account refresh in progress; retry the read shortly")
            return {**old, "refresh_lease": lease, "refresh_until": self.clock() + 60}

        leased = self.store.mutate("account_links", key_for(binding.subject), acquire)
        try:
            # Never perform an external exchange in a retried database transaction.
            tokens = exchange(self.cipher.open(leased["tokens"], binding.aad))

            def save(old):
                if (
                    old.get("generation") != binding.generation
                    or old.get("refresh_lease") != lease
                    or not old.get("active")
                ):
                    raise AccessDenied("Account changed during refresh; reconnect")
                result = {**old, "tokens": self.cipher.seal(tokens, binding.aad)}
                result.pop("refresh_lease", None)
                result.pop("refresh_until", None)
                return result

            self.store.mutate("account_links", key_for(binding.subject), save)
        finally:

            def release(old):
                if old.get("generation") == binding.generation and old.get("refresh_lease") == lease:
                    old.pop("refresh_lease", None)
                    old.pop("refresh_until", None)
                return old

            self.store.mutate("account_links", key_for(binding.subject), release)
        return self.credentials(binding)

    def take_state(self, token, kind):
        """Consume one-use session/link state before any external token exchange."""
        result = {}

        def consume(old):
            if old.get("kind") != kind or old.get("expires", 0) <= self.clock() or old.get("used"):
                raise AccessDenied("Session expired or callback already used; start again")
            result.update(old)
            return {"used": True, "expires": old["expires"], "kind": kind, "expires_at": old.get("expires_at")}

        self.store.mutate("web_state", key_for(token), consume)
        return result

    def new_state(self, kind, values, ttl=600):
        token = secrets.token_urlsafe(32)
        self.store.mutate(
            "web_state",
            key_for(token),
            lambda _: {
                **values,
                "kind": kind,
                "expires": self.clock() + ttl,
                "expires_at": datetime.fromtimestamp(self.clock() + ttl, tz=timezone.utc),
            },
        )
        return token

    def limit(self, subject):
        minute = int(self.clock() // 60)

        def change(old):
            count = old.get("count", 0) if old.get("minute") == minute else 0
            if count >= 60:
                raise AccessDenied("Plugin rate limit reached; retry next minute")
            return {
                "minute": minute,
                "count": count + 1,
                "expires_at": datetime.fromtimestamp(self.clock() + 120, tz=timezone.utc),
            }

        self.store.mutate("request_limits", key_for(subject), change)
