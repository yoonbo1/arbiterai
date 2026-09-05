"""Per-tenant key material. One module, imported by both services, so the worker and the
gateway can never disagree on how a tenant's key is derived:

  * worker/store.py encrypts the PHI map (phi_tokens.value_enc), job results (jobs.result_enc)
    and patient ids (patients.external_id_enc), and decrypts job requests;
  * gateway/main.py encrypts job requests on submit, decrypts a job's result only for
    GET /v1/jobs/{id}, and hashes patient ids for lookups.

The gateway image copies this file next to its own code (gateway/Dockerfile builds from
platform/ for exactly that reason); nothing here imports anything outside the standard library.

Local dev derives every key from TENANT_KEK. A deployment with real records replaces
tenant_key() with a per-tenant data-encryption key from a KMS or Vault, cached briefly."""
import hashlib, hmac, os


def tenant_key(tenant_id: str) -> str:
    """Passphrase for pgp_sym_encrypt / pgp_sym_decrypt of this tenant's rows."""
    kek = os.environ.get("TENANT_KEK")
    if not kek:
        raise RuntimeError("TENANT_KEK is not set; refusing to encrypt tenant data with a default key")
    return kek + tenant_id


def external_id_hash(tenant_id: str, external_id: str) -> str:
    """HMAC-SHA256 (hex) of a patient's external id under a key derived from the tenant key.
    Equality lookups only (patients.external_id_hash); the id itself is restored from
    external_id_enc. Keyed and domain-separated, so a table dump cannot be joined to a list of
    MRNs by hashing them, and the same MRN hashes differently for two tenants."""
    mac_key = hmac.new(tenant_key(tenant_id).encode(), b"patients.external_id", hashlib.sha256).digest()
    return hmac.new(mac_key, external_id.encode(), hashlib.sha256).hexdigest()
