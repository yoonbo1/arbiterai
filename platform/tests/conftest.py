"""Shared test setup. The environment is fixed here, BEFORE any module under test is imported:
gateway/auth.py reads API_KEY_PEPPER and worker/deid.py reads SPACY_MODEL at import time.

Nothing in these tests opens a network connection: the database, Redis and the embedding
service are replaced by the fakes below (or monkeypatched per test)."""
import os
import sys
from pathlib import Path

import pytest

PLATFORM = Path(__file__).resolve().parents[1]

# Hermetic, deliberately fake values. Set unconditionally so a developer's shell or
# platform/.env can never leak real settings (or a spaCy model that is not installed in the
# venv) into the unit tests. The URLs point at port 1 on loopback so an accidental connection
# attempt fails fast instead of reaching a real service.
os.environ.update({
    "API_KEY_PEPPER": "unit-test-pepper",
    "SPACY_MODEL": "en_core_web_sm",     # the worker default (en_core_web_lg) is not in .venv
    "DATABASE_URL": "postgresql://app_rw:x@127.0.0.1:1/unit_test_never_connected",
    "DATABASE_ADMIN_URL": "postgresql://hipaa:x@127.0.0.1:1/unit_test_never_connected",
    "REDIS_URL": "redis://:x@127.0.0.1:1/0",
    "TENANT_KEK": "unit-test-kek",
    "ADMIN_TOKEN": "unit-test-admin",
    "EMBED_URL": "http://127.0.0.1:1",
    "SMALL_MODEL_URL": "http://127.0.0.1:1/v1",
    "CHECKPOINTER": "none",
    "LANGCHAIN_TRACING_V2": "false",
})

# `import auth` works the way gateway/main.py does it (gateway/ is a flat directory, not a
# package); `from worker import deid, retrieval` needs platform/ on the path.
for _p in (PLATFORM, PLATFORM / "gateway"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


class FakeRedis:
    """Just enough of redis.asyncio (decode_responses=True) for gateway/auth.py: hashes with
    TTLs and INCR counters. Field values are stored as strings, exactly as the real client
    would hand them back, so int()/split() conversions in the code under test are exercised."""

    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}
        self.counters: dict[str, int] = {}
        self.expires: dict[str, int] = {}
        self.calls: list[tuple] = []

    async def hgetall(self, key):
        self.calls.append(("hgetall", key))
        return dict(self.hashes.get(key, {}))

    async def hset(self, key, mapping=None, **fields):
        fields = {**(mapping or {}), **fields}
        self.calls.append(("hset", key, fields))
        self.hashes.setdefault(key, {}).update({str(k): str(v) for k, v in fields.items()})
        return len(fields)

    async def expire(self, key, seconds):
        self.calls.append(("expire", key, seconds))
        if key in self.hashes or key in self.counters:
            self.expires[key] = int(seconds)
            return True
        return False

    async def incr(self, key, amount=1):
        self.calls.append(("incr", key))
        self.counters[key] = self.counters.get(key, 0) + amount
        return self.counters[key]

    async def delete(self, *keys):
        self.calls.append(("delete", *keys))
        n = 0
        for k in keys:
            if k in self.hashes or k in self.counters:
                n += 1
            self.hashes.pop(k, None)
            self.counters.pop(k, None)
            self.expires.pop(k, None)
        return n


class FakePool:
    """Stand-in for the asyncpg pool used by auth.resolve. fetchrow(sql, key_hash) returns the
    row registered under that hash (or None, as for an unknown/revoked/expired key) and records
    every query so tests can inspect the SQL text and bind parameters."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return self.rows.get(args[0]) if args else None


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def fake_pool():
    return FakePool()
