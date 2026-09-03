"""gateway/auth.py: key issuance and hashing, cached principal resolution, per-minute rate limit.
Async tests run under pytest-asyncio (asyncio_mode=auto in pytest.ini)."""
import time
import uuid

import pytest

import auth

TENANT = uuid.UUID("11111111-1111-4111-8111-111111111111")
KEY_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


def db_row(plaintext: str, rl: int = 100) -> dict:
    """What asyncpg hands back for the SELECT in auth.resolve: UUID columns, text[] as list."""
    return {"id": KEY_ID, "tenant_id": TENANT, "key_prefix": plaintext[:12],
            "scopes": ["ingest", "query"], "rate_limit_per_min": rl}


def principal(rl: int, key_id: str = "key-1") -> auth.Principal:
    return auth.Principal("tenant-1", key_id, "hipaa_live_x", ["query"], rl)


# ---------------------------------------------------------------- issuance / hashing

def test_new_key_shape_and_hash():
    plaintext, prefix, h = auth.new_key()
    assert auth.PREFIX == "hipaa_live_"
    assert plaintext.startswith(auth.PREFIX)
    assert len(plaintext) >= len(auth.PREFIX) + 43          # token_urlsafe(32) -> 43 chars
    assert prefix == plaintext[:12] and len(prefix) == 12
    assert h == auth.hash_key(plaintext)
    assert len(h) == 64 and int(h, 16) >= 0                  # hex-encoded SHA-256 digest
    assert plaintext not in h                                # the hash never exposes the key


def test_new_key_is_unique():
    keys = {auth.new_key()[0] for _ in range(25)}
    assert len(keys) == 25


def test_hash_key_is_deterministic_and_peppered(monkeypatch):
    plaintext = "hipaa_live_fixed-plaintext-for-this-test"
    h1 = auth.hash_key(plaintext)
    assert h1 == auth.hash_key(plaintext)
    assert auth.hash_key(plaintext + "x") != h1
    # rotating the pepper invalidates every stored hash (documented in .env.example)
    monkeypatch.setattr(auth, "PEPPER", b"a-different-pepper")
    assert auth.hash_key(plaintext) != h1


def test_pepper_comes_from_environment():
    assert auth.PEPPER == b"unit-test-pepper"      # set by tests/conftest.py before import


# ---------------------------------------------------------------- resolve

async def test_resolve_db_path_returns_principal_and_populates_cache(fake_pool, fake_redis):
    plaintext, prefix, h = auth.new_key()
    fake_pool.rows[h] = db_row(plaintext, rl=42)

    p = await auth.resolve(fake_pool, fake_redis, plaintext)

    assert p == auth.Principal(str(TENANT), str(KEY_ID), prefix, ["ingest", "query"], 42)
    assert isinstance(p.tenant_id, str) and isinstance(p.api_key_id, str)

    # one DB query, bound to the HMAC (never the plaintext), with every guard clause present
    assert len(fake_pool.calls) == 1
    sql, params = fake_pool.calls[0]
    assert params == (h,)
    assert plaintext not in sql
    for guard in ("k.revoked_at IS NULL", "k.expires_at IS NULL OR k.expires_at > now()",
                  "t.status='active'", "t.baa_signed_at IS NOT NULL"):
        assert guard in sql

    # cached under the hash with a 60 s TTL, as strings (what redis stores)
    assert fake_redis.hashes[f"key:{h}"] == {
        "tenant_id": str(TENANT), "id": str(KEY_ID), "prefix": prefix,
        "scopes": "ingest,query", "rl": "42"}
    assert fake_redis.expires[f"key:{h}"] == 60
    assert plaintext not in repr(fake_redis.hashes)


async def test_resolve_second_call_is_served_from_cache(fake_pool, fake_redis):
    plaintext, _, h = auth.new_key()
    fake_pool.rows[h] = db_row(plaintext)
    first = await auth.resolve(fake_pool, fake_redis, plaintext)

    del fake_pool.rows[h]      # the DB would now say "no such key"; the cache still answers
    second = await auth.resolve(fake_pool, fake_redis, plaintext)

    assert second == first
    assert len(fake_pool.calls) == 1
    assert isinstance(second.rate_limit_per_min, int)
    assert second.scopes == ["ingest", "query"]
    # the second call only touched the cache: hgetall, no hset/expire
    assert [c[0] for c in fake_redis.calls] == ["hgetall", "hset", "expire", "hgetall"]


async def test_resolve_warm_cache_never_hits_db(fake_pool, fake_redis):
    """Entry written by another gateway replica: no DB round trip at all."""
    plaintext, prefix, h = auth.new_key()
    fake_redis.hashes[f"key:{h}"] = {"tenant_id": "t1", "id": "k1", "prefix": prefix,
                                     "scopes": "query", "rl": "7"}
    p = await auth.resolve(fake_pool, fake_redis, plaintext)
    assert p == auth.Principal("t1", "k1", prefix, ["query"], 7)
    assert fake_pool.calls == []


async def test_resolve_unknown_or_revoked_key_returns_none(fake_pool, fake_redis):
    plaintext, _, h = auth.new_key()
    # revoked, expired and never-issued keys all fall out of the WHERE clause -> no row
    assert await auth.resolve(fake_pool, fake_redis, plaintext) is None
    assert len(fake_pool.calls) == 1
    assert f"key:{h}" not in fake_redis.hashes         # negative results are not cached
    assert fake_redis.expires == {}


async def test_resolve_wrong_plaintext_does_not_match(fake_pool, fake_redis):
    plaintext, _, h = auth.new_key()
    fake_pool.rows[h] = db_row(plaintext)
    assert await auth.resolve(fake_pool, fake_redis, plaintext) is not None
    tampered = plaintext[:-1] + ("A" if plaintext[-1] != "A" else "B")
    assert await auth.resolve(fake_pool, fake_redis, tampered) is None
    assert await auth.resolve(fake_pool, fake_redis, "") is None
    assert len(fake_pool.calls) == 3


# ---------------------------------------------------------------- rate limiting

async def test_rate_limited_allows_limit_then_rejects(fake_redis, monkeypatch):
    now = 1_700_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)     # pin the minute bucket
    p = principal(3)

    verdicts = [await auth.rate_limited(fake_redis, p) for _ in range(5)]

    assert verdicts == [False, False, False, True, True]
    bucket = f"rl:{p.api_key_id}:{int(now // 60)}"
    assert fake_redis.counters == {bucket: 5}
    assert fake_redis.expires == {bucket: 90}
    # the 90 s expiry is set exactly once, on the first hit of the minute
    assert [c for c in fake_redis.calls if c[0] == "expire"] == [("expire", bucket, 90)]


async def test_rate_limit_resets_in_the_next_minute(fake_redis, monkeypatch):
    now = 1_700_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    p = principal(1)
    assert await auth.rate_limited(fake_redis, p) is False
    assert await auth.rate_limited(fake_redis, p) is True

    monkeypatch.setattr(time, "time", lambda: now + 60)
    assert await auth.rate_limited(fake_redis, p) is False
    assert len(fake_redis.counters) == 2
    assert all(ttl == 90 for ttl in fake_redis.expires.values())


async def test_rate_limit_buckets_are_per_key(fake_redis, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
    a, b = principal(1, "key-a"), principal(1, "key-b")
    assert await auth.rate_limited(fake_redis, a) is False
    assert await auth.rate_limited(fake_redis, a) is True
    assert await auth.rate_limited(fake_redis, b) is False     # a's burst does not affect b


async def test_rate_limit_zero_rejects_everything(fake_redis, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
    assert await auth.rate_limited(fake_redis, principal(0)) is True
