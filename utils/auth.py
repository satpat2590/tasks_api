import json
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, Set

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AgentPrincipal:
    name: str
    scopes: frozenset[str]


def _normalize_scopes(raw_scopes: Iterable[str] | None) -> frozenset[str]:
    scopes: Set[str] = set()
    for scope in raw_scopes or []:
        normalized = str(scope).strip().lower()
        if normalized:
            scopes.add(normalized)

    if "write" in scopes:
        scopes.add("read")

    if not scopes:
        scopes.update({"read", "write"})

    return frozenset(scopes)


def _register_token(
    registry: Dict[str, AgentPrincipal],
    name: str,
    token: str | None,
    scopes: Iterable[str] | None = None,
) -> None:
    if not token:
        return
    registry[token.strip()] = AgentPrincipal(name=name, scopes=_normalize_scopes(scopes))


@lru_cache(maxsize=1)
def load_agent_registry() -> Dict[str, AgentPrincipal]:
    registry: Dict[str, AgentPrincipal] = {}

    raw_json = os.getenv("ATMA_AGENT_TOKENS_JSON")
    if raw_json:
        parsed = json.loads(raw_json)
        if isinstance(parsed, dict):
            for agent_name, config in parsed.items():
                if isinstance(config, str):
                    _register_token(registry, agent_name, config, ("read", "write"))
                    continue

                if not isinstance(config, dict):
                    raise ValueError("ATMA_AGENT_TOKENS_JSON object entries must be strings or objects")

                _register_token(
                    registry,
                    config.get("name", agent_name),
                    config.get("token"),
                    config.get("scopes"),
                )
        elif isinstance(parsed, list):
            for config in parsed:
                if not isinstance(config, dict):
                    raise ValueError("ATMA_AGENT_TOKENS_JSON list entries must be objects")
                _register_token(
                    registry,
                    config.get("name", "agent"),
                    config.get("token"),
                    config.get("scopes"),
                )
        else:
            raise ValueError("ATMA_AGENT_TOKENS_JSON must be a JSON object or array")

    _register_token(registry, "hermes", os.getenv("ATMA_HERMES_TOKEN"), ("read", "write"))
    _register_token(registry, "atma-agent", os.getenv("ATMA_AGENT_TOKEN"), ("read", "write"))
    _register_token(registry, "atma-readonly", os.getenv("ATMA_READONLY_AGENT_TOKEN"), ("read",))
    _register_token(registry, "Argus", os.getenv("ATMA_ARGUS_TOKEN"), ("read", "write"))
    _register_token(registry, "Veltiosi", os.getenv("ATMA_VELTIOSI_TOKEN"), ("read", "write"))
    _register_token(registry, "Gyani", os.getenv("ATMA_GYANI_TOKEN"), ("read", "write"))

    return registry


# Map agent principal names to users table names for task scoping
AGENT_TO_USER_MAP = {
    "hermes": "Satyam",
    "atma-agent": "Satyam",
    "atma-readonly": "Satyam",
    "Argus": "Argus",
    "Veltiosi": "Veltiosi",
    "Gyani": "Satyam",
}


def authenticate_agent(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AgentPrincipal:
    try:
        registry = load_agent_registry()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid agent auth configuration: {exc}",
        ) from exc

    if not registry:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent auth is not configured on this Atma service",
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    presented = credentials.credentials.strip()
    for token, principal in registry.items():
        if secrets.compare_digest(token, presented):
            return principal

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid agent token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_agent_scope(required_scope: str):
    normalized_scope = required_scope.strip().lower()

    def dependency(principal: AgentPrincipal = Depends(authenticate_agent)) -> AgentPrincipal:
        if normalized_scope not in principal.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Agent '{principal.name}' does not have '{normalized_scope}' scope",
            )
        return principal

    return dependency


require_read_agent = require_agent_scope("read")
require_write_agent = require_agent_scope("write")
