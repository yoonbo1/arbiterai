"""worker/tenant_keys.py: the one derivation both services use for per-tenant encryption keys
and for the keyed patient-id hash. Also pins that the gateway and the worker really import this
module rather than carrying their own copy."""
import ast
import hashlib
import hmac
import sys
from pathlib import Path

import pytest

from worker import store, tenant_keys

T_A = "11111111-1111-4111-8111-111111111111"
T_B = "22222222-2222-4222-8222-222222222222"


# ---------------------------------------------------------------- tenant_key

def test_tenant_key_is_kek_plus_tenant_id_and_differs_per_tenant():
    assert tenant_keys.tenant_key(T_A) == "unit-test-kek" + T_A       # TENANT_KEK from conftest.py
    assert tenant_keys.tenant_key(T_A) != tenant_keys.tenant_key(T_B)


def test_tenant_key_refuses_to_run_without_a_kek(monkeypatch):
    monkeypatch.delenv("TENANT_KEK")
    with pytest.raises(RuntimeError, match="TENANT_KEK"):
        tenant_keys.tenant_key(T_A)
    monkeypatch.setenv("TENANT_KEK", "")
    with pytest.raises(RuntimeError):
        tenant_keys.tenant_key(T_A)


def test_tenant_key_rotates_with_the_kek(monkeypatch):
    before = tenant_keys.tenant_key(T_A)
    monkeypatch.setenv("TENANT_KEK", "another-kek")
    assert tenant_keys.tenant_key(T_A) != before


# ---------------------------------------------------------------- external_id_hash

def test_external_id_hash_is_hex_sha256_and_deterministic():
    h = tenant_keys.external_id_hash(T_A, "P00001")
    assert len(h) == 64 and int(h, 16) >= 0
    assert h == tenant_keys.external_id_hash(T_A, "P00001")


def test_external_id_hash_is_keyed_domain_separated_and_per_tenant():
    h = tenant_keys.external_id_hash(T_A, "P00001")
    assert h != hashlib.sha256(b"P00001").hexdigest()                 # not a bare hash of the MRN
    passphrase = tenant_keys.tenant_key(T_A).encode()
    assert h != hmac.new(passphrase, b"P00001", hashlib.sha256).hexdigest()   # not directly under the pgp key
    assert h != tenant_keys.external_id_hash(T_B, "P00001")           # same MRN, other tenant
    assert h != tenant_keys.external_id_hash(T_A, "P00002")
    assert "P00001" not in h


def test_external_id_hash_matches_the_documented_construction():
    """HMAC-SHA256(HMAC-SHA256(tenant_key, 'patients.external_id'), external_id): pinned so a
    change here cannot silently orphan every stored patient row."""
    mac_key = hmac.new(tenant_keys.tenant_key(T_A).encode(), b"patients.external_id", hashlib.sha256).digest()
    assert tenant_keys.external_id_hash(T_A, "MRN-42") == hmac.new(mac_key, b"MRN-42", hashlib.sha256).hexdigest()


def test_external_id_hash_rotates_with_the_kek(monkeypatch):
    before = tenant_keys.external_id_hash(T_A, "P00001")
    monkeypatch.setenv("TENANT_KEK", "another-kek")
    assert tenant_keys.external_id_hash(T_A, "P00001") != before


# ---------------------------------------------------------------- one module, both services

def test_module_is_standard_library_only():
    """The gateway image has none of the worker's packages; the module must import nowhere else."""
    tree = ast.parse(Path(tenant_keys.__file__).read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names and names <= sys.stdlib_module_names, names


def test_worker_store_uses_the_shared_derivation():
    assert store.tenant_key is tenant_keys.tenant_key
    assert store.external_id_hash is tenant_keys.external_id_hash
    assert not hasattr(store, "_tenant_key")                          # the private copy is gone


def test_gateway_uses_the_shared_derivation():
    pytest.importorskip("fastapi")
    pytest.importorskip("asyncpg")
    import main as gateway
    assert gateway.tenant_key is tenant_keys.tenant_key
    assert gateway.external_id_hash is tenant_keys.external_id_hash
