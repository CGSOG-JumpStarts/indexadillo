"""Validate access tokens independently of caller-supplied identity headers."""

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from core.config import TenantScope, required, scopes


class AccessDenied(Exception):
    def __init__(self, status: int = 403):
        self.status = status


@dataclass(frozen=True)
class Principal:
    subject: str
    scope: TenantScope
    roles: frozenset[str]
    groups: tuple[str, ...]


@lru_cache
def signing_keys() -> PyJWKClient:
    tenant = required("ENTRA_TENANT_ID")
    return PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys", cache_keys=True)


def authorize(headers, role: str) -> Principal:
    if os.getenv("AUTH_MODE", "entra") == "local":
        if os.getenv("WEBSITE_INSTANCE_ID") or os.getenv("WEBSITE_HOSTNAME"):
            raise AccessDenied(403)
        scope = scopes()[required("LOCAL_SCOPE_KEY")]
        return Principal("local-developer", scope, frozenset({"Operator"}), ())
    value = headers.get("Authorization", "")
    if not value.startswith("Bearer ") or len(value) > 32768:
        raise AccessDenied(401)
    token = value[7:]
    try:
        claims = jwt.decode(
            token,
            signing_keys().get_signing_key_from_jwt(token).key,
            algorithms=["RS256"],
            audience=required("ENTRA_AUDIENCE"),
            issuer=f"https://login.microsoftonline.com/{required('ENTRA_TENANT_ID')}/v2.0",
            options={"require": ["exp", "iat", "iss", "aud", "tid", "oid"]},
        )
    except (jwt.PyJWTError, jwt.PyJWKClientError, ValueError) as exc:
        raise AccessDenied(401) from exc
    if claims["tid"] != required("ENTRA_TENANT_ID"):
        raise AccessDenied()
    roles = frozenset(str(r).removeprefix("Indexadillo.") for r in claims.get("roles", []))
    if "Operator" not in roles and role not in roles:
        raise AccessDenied()
    # Map an application identity first, then an explicitly configured Entra tenant.
    routing = scopes()
    scope = routing.get(f"{claims['tid']}:{claims['oid']}") or routing.get(claims["tid"])
    if scope is None or claims.get("hasgroups") or "groups" in claims.get("_claim_names", {}):
        raise AccessDenied()
    return Principal(claims["oid"], scope, roles, tuple(claims.get("groups", [])))


def permitted_index(principal: Principal, name: str | None, *, for_query=False) -> str:
    alias = principal.scope.query_alias if for_query else None
    selected = name or alias or principal.scope.indexes[0]
    allowed = principal.scope.indexes + ([alias] if alias else [])
    if selected not in allowed:
        raise AccessDenied()
    return selected


def permitted_prefixes(scope: TenantScope, prefixes: list[str]) -> list[str]:
    if not prefixes or len(prefixes) > 32:
        raise ValueError("Provide 1 to 32 source prefixes")
    result = []
    for prefix in prefixes:
        if len(prefix) > 1024 or ".." in prefix.split("/") or "\\" in prefix:
            raise ValueError("Invalid source prefix")
        # Empty means all documents in the caller's configured tenant root.
        prefix = prefix or scope.prefix
        if not prefix.startswith(scope.prefix):
            raise AccessDenied()
        result.append(prefix)
    return list(dict.fromkeys(result))


def security_filter(principal: Principal) -> str:
    def escape(value: str) -> str:
        return value.replace("'", "''")

    groups = [g for g in principal.groups if "," not in g]
    tenant = f"tenant_id eq '{escape(principal.scope.tenant_id)}'"
    visible = "visibility eq 'tenant'"
    if groups:
        visible += f" or allowed_groups/any(g: search.in(g, '{escape(','.join(groups))}', ','))"
    return f"{tenant} and ({visible})"


def current_source_allowed(principal: Principal, name: str, props, expected_etag: str) -> bool:
    """Revalidate against current source metadata before returning indexed text."""
    if not name.startswith(principal.scope.prefix) or props is None or str(props.etag) != expected_etag:
        return False
    metadata = props.metadata or {}
    groups = {value.strip() for value in metadata.get("allowed_groups", "").split(",") if value.strip()}
    groups = groups or set(principal.scope.default_groups)
    visibility = metadata.get("visibility", "restricted" if groups else "tenant")
    if principal.scope.default_groups:
        visibility = "restricted"
    return visibility == "tenant" or (
        visibility == "restricted" and bool(groups.intersection(principal.groups))
    )
