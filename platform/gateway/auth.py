"""API key issuance and verification. Plaintext keys are shown once and never stored."""
import hashlib, hmac, os, secrets
from dataclasses import dataclass

PEPPER = os.environ["API_KEY_PEPPER"].encode()
PREFIX = "hipaa_live_"


def new_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix, hash)."""
    plaintext = PREFIX + secrets.token_urlsafe(32)
    return plaintext, plaintext[:12], hash_key(plaintext)


def hash_key(plaintext: str) -> str:
    return hmac.new(PEPPER, plaintext.encode(), hashlib.sha256).hexdigest()


@dataclass
class Principal:
    tenant_id: str
    api_key_id: str
    key_prefix: str
    scopes: list[str]
    rate_limit_per_min: int


async def resolve(pool, redis, plaintext: str) -> Principal | None:
    """Hash -> cache -> DB. Tenant is derived from the key, never supplied by the client."""
    h = hash_key(plaintext)
    cached = await redis.hgetall(f"key:{h}")
    if cached:
        return Principal(cached["tenant_id"], cached["id"], cached["prefix"],
                         cached["scopes"].split(","), int(cached["rl"]))
    row = await pool.fetchrow(
        """SELECT k.id, k.tenant_id, k.key_prefix, k.scopes, k.rate_limit_per_min
             FROM api_keys k JOIN tenants t ON t.id = k.tenant_id
            WHERE k.key_hash=$1 AND k.revoked_at IS NULL
              AND (k.expires_at IS NULL OR k.expires_at > now())
              AND t.status='active' AND t.baa_signed_at IS NOT NULL""", h)
    if not row:
        return None
    p = Principal(str(row["tenant_id"]), str(row["id"]), row["key_prefix"],
                  list(row["scopes"]), row["rate_limit_per_min"])
    await redis.hset(f"key:{h}", mapping={"tenant_id": p.tenant_id, "id": p.api_key_id,
                     "prefix": p.key_prefix, "scopes": ",".join(p.scopes), "rl": p.rate_limit_per_min})
    await redis.expire(f"key:{h}", 60)   # short TTL so revocation lands within a minute
    return p


async def rate_limited(redis, p: Principal) -> bool:
    import time
    bucket = f"rl:{p.api_key_id}:{int(time.time() // 60)}"
    n = await redis.incr(bucket)
    if n == 1:
        await redis.expire(bucket, 90)
    return n > p.rate_limit_per_min
