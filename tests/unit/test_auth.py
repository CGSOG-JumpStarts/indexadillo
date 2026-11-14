import json
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from core.auth import (
    AccessDenied,
    Principal,
    authorize,
    current_source_allowed,
    permitted_index,
    permitted_prefixes,
    security_filter,
)
from core.config import TenantScope, scopes


@pytest.fixture
def token_factory(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        "core.auth.signing_keys",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())),
    )

    def create(**overrides):
        claims = {
            "exp": time.time() + 600,
            "iat": time.time(),
            "iss": "https://login.microsoftonline.com/tenant-a/v2.0",
            "aud": "api-client",
            "tid": "tenant-a",
            "oid": "caller",
            "roles": ["Indexadillo.Reader"],
        }
        claims.update(overrides)
        return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256")}

    return create


def test_missing_token_and_forged_identity_header_are_rejected():
    with pytest.raises(AccessDenied) as exc:
        authorize({"X-MS-CLIENT-PRINCIPAL": "forged"}, "Reader")
    assert exc.value.status == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "other-api"},
        {"tid": "other-tenant"},
        {"exp": time.time() - 1},
        {"iss": "https://attacker.test"},
        {"roles": []},
        {"hasgroups": True},
    ],
)
def test_invalid_token_or_permissions_fail_closed(token_factory, overrides):
    with pytest.raises(AccessDenied):
        authorize(token_factory(**overrides), "Reader")


def test_signed_token_roles_and_scopes(token_factory):
    principal = authorize(token_factory(groups=["allowed-group"]), "Reader")
    assert principal.scope.prefix == "tenants/a/"
    assert principal.groups == ("allowed-group",)
    with pytest.raises(AccessDenied):
        authorize(token_factory(), "Indexer")
    assert authorize(token_factory(roles=["Indexadillo.Operator"]), "Indexer").subject == "caller"


def test_index_and_prefix_cannot_escape_tenant():
    scope = scopes()["tenant-a"]
    principal = Principal("caller", scope, frozenset({"Reader"}), ())
    with pytest.raises(AccessDenied):
        permitted_index(principal, "another-tenant")
    assert permitted_prefixes(scope, [""]) == ["tenants/a/"]
    with pytest.raises(AccessDenied):
        permitted_prefixes(scope, ["tenants/b/"])
    with pytest.raises(ValueError):
        permitted_prefixes(scope, ["tenants/a/../b/"])


def test_overlapping_source_roots_are_rejected(monkeypatch):
    monkeypatch.setenv(
        "TENANT_SCOPES_JSON",
        json.dumps(
            {
                "a": {"tenant_id": "a", "prefix": "a/", "indexes": ["index"]},
                "b": {"tenant_id": "b", "prefix": "a/b/", "indexes": ["index"]},
            }
        ),
    )
    scopes.cache_clear()
    with pytest.raises(ValueError, match="overlap"):
        scopes()


def test_local_auth_bypass_is_impossible_on_azure(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("WEBSITE_HOSTNAME", "app.azurewebsites.net")
    with pytest.raises(AccessDenied):
        authorize({}, "Operator")


def test_security_filter_escapes_group_values():
    scope = TenantScope(tenant_id="tenant-a", prefix="a/", indexes=["index"])
    value = security_filter(Principal("caller", scope, frozenset(), ("g' or true",)))
    assert "g'' or true" in value
    assert value.startswith("tenant_id eq 'tenant-a' and (")


def test_source_permission_changes_and_cross_tenant_paths_fail_closed():
    principal = Principal("caller", scopes()["tenant-a"], frozenset({"Reader"}), ("permitted",))
    props = SimpleNamespace(etag="v1", metadata={"allowed_groups": "permitted", "visibility": "restricted"})
    assert current_source_allowed(principal, "tenants/a/report.pdf", props, "v1")
    assert not current_source_allowed(principal, "tenants/b/report.pdf", props, "v1")
    assert not current_source_allowed(principal, "tenants/a/report.pdf", props, "old")
    props.metadata["allowed_groups"] = "revoked"
    assert not current_source_allowed(principal, "tenants/a/report.pdf", props, "v1")
