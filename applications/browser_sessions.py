"""Server-issued browser sessions bound to a declared credential verifier.

The verifier is an injected adapter. It is the only source of principal,
tenant, and role. Request bodies, headers, and cookies cannot nominate those
identifiers. Session cookies are opaque, HMAC-bound, HttpOnly, and limited by
an absolute expiry. A missing adapter or signing key does not become
trusted-local access.

This module does not read process environment, profile files, or case
artifacts. Authentication failures expose a fixed reason code and nothing else.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Protocol
from urllib.parse import urlsplit

from .principal_store import PrincipalStore, PrincipalStoreError

TASK_ID = "CIMP-GUI-05"
SESSION_COOKIE = "cg_session"
CSRF_HEADER = "x-csrf-token"
_MAX_TTL_SECONDS = 3600
_MIN_KEY_BYTES = 32
_ROLE_FIELDS = frozenset({
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
})
_IDENTITY_FIELDS = frozenset({"user_id", "principal_id", "tenant_id", *_ROLE_FIELDS})
_HEADER_FIELDS = (
    ("x-user-id", "user_id"),
    ("x-principal-id", "principal_id"),
    ("x-tenant-id", "tenant_id"),
    ("x-role", "role"),
)
_PUBLIC_CODES = frozenset({
    "authentication_failed",
    "authentication_unavailable",
    "session_required",
    "session_expired",
    "csrf_rejected",
    "identifier_rejected",
})
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class BrowserSessionError(Exception):
    """Fail-closed session error. ``code`` is the only public text."""

    def __init__(self, code: str) -> None:
        self.code = code if code in _PUBLIC_CODES else "authentication_failed"
        super().__init__(self.code)


def browser_session_http_status(error: BrowserSessionError) -> tuple[int, str]:
    status = {
        "authentication_failed": 401,
        "authentication_unavailable": 503,
        "session_required": 401,
        "session_expired": 401,
        "csrf_rejected": 403,
        "identifier_rejected": 403,
    }
    return status[error.code], error.code


@dataclass(frozen=True)
class VerifiedPrincipal:
    """Identity produced by the credential adapter, never by the request."""

    principal_id: str
    tenant_id: str
    roles: tuple[str, ...]


class CredentialVerificationAdapter(Protocol):
    """Declared verifier. Implementations must not trust caller-supplied roles."""

    def verify_credential(self, material: Mapping[str, Any]) -> VerifiedPrincipal:
        """Return the server principal for this secret or raise a closed error."""


@dataclass(frozen=True)
class BrowserSessionConfiguration:
    """Explicit session settings. An incomplete value fails closed."""

    adapter: Optional[CredentialVerificationAdapter]
    signing_key: Optional[bytes]
    ttl_seconds: int = 900

    def complete(self) -> bool:
        adapter = self.adapter
        key = self.signing_key
        ttl = self.ttl_seconds
        if adapter is None or not callable(getattr(adapter, "verify_credential", None)):
            return False
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview):
            return False
        if len(bytes(key)) < _MIN_KEY_BYTES:
            return False
        if type(ttl) is not int or not 1 <= ttl <= _MAX_TTL_SECONDS:
            return False
        return True


@dataclass(frozen=True)
class IssuedBrowserSession:
    token: str
    csrf_token: str
    principal_id: str
    tenant_id: str
    roles: tuple[str, ...]
    expires_at: int
    absolute_expires_at: int
    generation: int

    def public_view(self) -> dict[str, Any]:
        return {
            "authenticated": True,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "roles": list(self.roles),
            "expires_at": self.expires_at,
            "absolute_expires_at": self.absolute_expires_at,
            "csrf_token": self.csrf_token,
            "generation": self.generation,
        }


@dataclass
class _Record:
    principal_id: str
    tenant_id: str
    roles: tuple[str, ...]
    csrf_token: str
    expires_at: float
    absolute_expires_at: float
    generation: int


@dataclass(frozen=True)
class BoundBrowserSession:
    principal_id: str
    tenant_id: str
    roles: tuple[str, ...]
    expires_at: int
    absolute_expires_at: int
    generation: int

    def public_view(self) -> dict[str, Any]:
        return {
            "authenticated": True,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "roles": list(self.roles),
            "expires_at": self.expires_at,
            "absolute_expires_at": self.absolute_expires_at,
            "generation": self.generation,
        }


class PrincipalStoreCredentialAdapter:
    """Verify a synthetic secret, then load roles from the server-owned roster.

    The secret map is injected by the operator. Request fields are not read.
    Store failures collapse to the same authentication failure as a bad secret.
    """

    def __init__(self, store: PrincipalStore, credentials: Mapping[str, str]) -> None:
        if not isinstance(credentials, Mapping) or not credentials:
            raise BrowserSessionError("authentication_unavailable")
        mapped: dict[str, str] = {}
        for secret, principal_id in credentials.items():
            if not isinstance(secret, str) or secret == "" or not isinstance(principal_id, str) or principal_id == "":
                raise BrowserSessionError("authentication_unavailable")
            mapped[secret] = principal_id
        self._store = store
        self._credentials = mapped

    def verify_credential(self, material: Mapping[str, Any]) -> VerifiedPrincipal:
        secret = material.get("credential") if isinstance(material, Mapping) else None
        principal_id = self._credentials.get(secret) if isinstance(secret, str) else None
        if principal_id is None:
            raise BrowserSessionError("authentication_failed")
        try:
            record = self._store.load(principal_id)
        except PrincipalStoreError:
            raise BrowserSessionError("authentication_failed") from None
        if record.status != "active" or not record.roles:
            raise BrowserSessionError("authentication_failed")
        return VerifiedPrincipal(record.principal_id, record.tenant_id, tuple(record.roles))


class BrowserSessionService:
    """Issue, rotate, and revoke bounded browser sessions."""

    def __init__(
        self,
        configuration: Optional[BrowserSessionConfiguration],
        *,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._clock = clock or time.time
        self._records: dict[str, _Record] = {}
        self._by_principal: dict[str, str] = {}
        if configuration is None or not configuration.complete():
            self._configured = False
            self._adapter: Optional[CredentialVerificationAdapter] = None
            self._key = b""
            self._ttl = 0
            return
        assert configuration.adapter is not None
        assert configuration.signing_key is not None
        self._configured = True
        self._adapter = configuration.adapter
        self._key = bytes(configuration.signing_key)
        self._ttl = configuration.ttl_seconds

    @classmethod
    def unavailable(cls, *, clock: Optional[Callable[[], float]] = None) -> "BrowserSessionService":
        return cls(None, clock=clock)

    @property
    def configured(self) -> bool:
        return self._configured

    def login(self, payload: Mapping[str, Any]) -> IssuedBrowserSession:
        self._require_configured()
        if not isinstance(payload, Mapping):
            raise BrowserSessionError("authentication_failed")
        if any(field in payload for field in _IDENTITY_FIELDS):
            raise BrowserSessionError("identifier_rejected")
        credential = payload.get("credential")
        if not isinstance(credential, str) or credential == "":
            raise BrowserSessionError("authentication_failed")
        verified = self._verify({"credential": credential})
        return self._issue(verified, generation=1, absolute_expires_at=None)

    def rotate(self, token: str, *, csrf_token: str) -> IssuedBrowserSession:
        record_id, record = self._open_token(token)
        self._check_csrf(record, csrf_token)
        verified = VerifiedPrincipal(record.principal_id, record.tenant_id, record.roles)
        absolute = record.absolute_expires_at
        self._drop(record_id)
        return self._issue(verified, generation=record.generation + 1, absolute_expires_at=absolute)

    def logout(self, token: str, *, csrf_token: str) -> None:
        record_id, record = self._open_token(token)
        self._check_csrf(record, csrf_token)
        self._drop(record_id)

    def authenticate_token(self, token: Optional[str]) -> BoundBrowserSession:
        _record_id, record = self._open_token(token or "")
        return _bound(record)

    def resume(self, token: str, *, bound: BoundBrowserSession) -> dict[str, Any]:
        """Read the current transport token after reauthenticating its binding.

        This does not issue, rotate, or extend a session. Keep CSRF out of the
        ordinary principal projection, which is used beyond this owned read.
        """
        _record_id, record = self._open_token(token)
        current = _bound(record)
        if type(bound) is not BoundBrowserSession or current != bound:
            raise BrowserSessionError("authentication_failed")
        return {**current.public_view(), "csrf_token": record.csrf_token}

    def resume_http(self, request: Any, *, bound: BoundBrowserSession) -> dict[str, Any]:
        """Expose the existing CSRF token only through a same-origin read."""
        _require_resume_origin(request)
        token = str(request.cookies.get(SESSION_COOKIE) or "")
        return self.resume(token, bound=bound)

    async def bind_http(self, request: Any, *, allow_anonymous: bool) -> Optional[BoundBrowserSession]:
        """Resolve one HTTP request. Anonymous is only the login route.

        A missing configuration raises ``authentication_unavailable`` for every
        protected route. It never returns trusted-local authority.
        """

        presented = await _presented_identifiers(request)
        if not self._configured:
            if allow_anonymous:
                return None
            raise BrowserSessionError("authentication_unavailable")
        if _asserts_role(presented) or (allow_anonymous and presented):
            raise BrowserSessionError("identifier_rejected")
        token = ""
        cookies = getattr(request, "cookies", {}) or {}
        if hasattr(cookies, "get"):
            token = str(cookies.get(SESSION_COOKIE) or "")
        if allow_anonymous:
            return None
        bound_id, record = self._open_token(token)
        if _conflicts(presented, record):
            raise BrowserSessionError("identifier_rejected")
        if request.method.upper() in _UNSAFE_METHODS:
            header_csrf = str(request.headers.get(CSRF_HEADER) or "")
            self._check_csrf(record, header_csrf)
        # Touch the id so a static analyzer sees the lookup retained the record.
        if bound_id not in self._records:
            raise BrowserSessionError("session_required")
        return _bound(record)

    def attach_session_cookie(self, response: Any, issued: IssuedBrowserSession) -> None:
        remaining = max(0, issued.expires_at - int(self._clock()))
        response.set_cookie(
            key=SESSION_COOKIE,
            value=issued.token,
            max_age=remaining,
            path="/",
            secure=True,
            httponly=True,
            samesite="strict",
        )

    def clear_session_cookie(self, response: Any) -> None:
        response.delete_cookie(
            key=SESSION_COOKIE,
            path="/",
            secure=True,
            httponly=True,
            samesite="strict",
        )

    def _require_configured(self) -> None:
        if not self._configured or self._adapter is None:
            raise BrowserSessionError("authentication_unavailable")

    def _verify(self, material: Mapping[str, Any]) -> VerifiedPrincipal:
        self._require_configured()
        assert self._adapter is not None
        try:
            verified = self._adapter.verify_credential(material)
        except BrowserSessionError as exc:
            if exc.code != "authentication_failed":
                raise BrowserSessionError("authentication_failed") from None
            raise
        except Exception:
            raise BrowserSessionError("authentication_failed") from None
        if not isinstance(verified, VerifiedPrincipal):
            raise BrowserSessionError("authentication_failed")
        if not _opaque(verified.principal_id) or not _opaque(verified.tenant_id):
            raise BrowserSessionError("authentication_failed")
        if verified.principal_id == verified.tenant_id:
            raise BrowserSessionError("authentication_failed")
        if not verified.roles or not all(isinstance(role, str) and role.strip() for role in verified.roles):
            raise BrowserSessionError("authentication_failed")
        return VerifiedPrincipal(verified.principal_id, verified.tenant_id, tuple(verified.roles))

    def _issue(
        self,
        verified: VerifiedPrincipal,
        *,
        generation: int,
        absolute_expires_at: Optional[float],
    ) -> IssuedBrowserSession:
        now = float(self._clock())
        absolute = now + self._ttl if absolute_expires_at is None else float(absolute_expires_at)
        expires = min(now + self._ttl, absolute)
        if expires <= now:
            raise BrowserSessionError("session_expired")
        previous = self._by_principal.get(verified.principal_id)
        if previous is not None:
            self._drop(previous)
        session_id = secrets.token_urlsafe(32)
        record = _Record(
            principal_id=verified.principal_id,
            tenant_id=verified.tenant_id,
            roles=verified.roles,
            csrf_token=secrets.token_urlsafe(32),
            expires_at=expires,
            absolute_expires_at=absolute,
            generation=generation,
        )
        self._records[session_id] = record
        self._by_principal[verified.principal_id] = session_id
        return IssuedBrowserSession(
            token=self._seal(session_id),
            csrf_token=record.csrf_token,
            principal_id=record.principal_id,
            tenant_id=record.tenant_id,
            roles=record.roles,
            expires_at=int(expires),
            absolute_expires_at=int(absolute),
            generation=generation,
        )

    def _open_token(self, token: str) -> tuple[str, _Record]:
        self._require_configured()
        session_id = self._unseal(token)
        record = self._records.get(session_id)
        if record is None:
            raise BrowserSessionError("authentication_failed")
        now = float(self._clock())
        if now >= record.expires_at or now >= record.absolute_expires_at:
            self._drop(session_id)
            raise BrowserSessionError("session_expired")
        return session_id, record

    def _check_csrf(self, record: _Record, presented: str) -> None:
        if not isinstance(presented, str) or presented == "":
            raise BrowserSessionError("csrf_rejected")
        if not hmac.compare_digest(presented, record.csrf_token):
            raise BrowserSessionError("csrf_rejected")

    def _seal(self, session_id: str) -> str:
        mac = hmac.new(self._key, session_id.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{session_id}.{mac}"

    def _unseal(self, token: str) -> str:
        if not isinstance(token, str) or token.count(".") != 1:
            raise BrowserSessionError("session_required" if token == "" else "authentication_failed")
        session_id, mac = token.split(".", 1)
        if session_id == "" or len(mac) != 64:
            raise BrowserSessionError("authentication_failed")
        expected = hmac.new(self._key, session_id.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            raise BrowserSessionError("authentication_failed")
        return session_id

    def _drop(self, session_id: str) -> None:
        record = self._records.pop(session_id, None)
        if record is None:
            return
        current = self._by_principal.get(record.principal_id)
        if current == session_id:
            self._by_principal.pop(record.principal_id, None)


def resolve_browser_session_service(
    configuration: Optional[BrowserSessionConfiguration],
    *,
    clock: Optional[Callable[[], float]] = None,
) -> BrowserSessionService:
    """Build the runtime service. Incomplete configuration is unavailable."""

    if configuration is None or not configuration.complete():
        return BrowserSessionService.unavailable(clock=clock)
    return BrowserSessionService(configuration, clock=clock)


def _bound(record: _Record) -> BoundBrowserSession:
    return BoundBrowserSession(
        principal_id=record.principal_id,
        tenant_id=record.tenant_id,
        roles=record.roles,
        expires_at=int(record.expires_at),
        absolute_expires_at=int(record.absolute_expires_at),
        generation=record.generation,
    )


def _require_resume_origin(request: Any) -> None:
    # Fetch metadata is supplemental: browsers may omit it, and non-browser
    # clients still authenticate with the actual signed cookie. Never treat
    # caller-supplied Forwarded headers as authority for the request origin.
    sites = request.headers.getlist("sec-fetch-site")
    if len(sites) > 1 or (sites and sites[0] not in {"same-origin", "none"}):
        raise BrowserSessionError("csrf_rejected")
    origins = request.headers.getlist("origin")
    if not origins:
        return
    if len(origins) != 1:
        raise BrowserSessionError("csrf_rejected")
    try:
        origin = urlsplit(origins[0])
        target = urlsplit(str(request.url))
        if (origin.scheme.lower() not in {"http", "https"} or not origin.hostname
                or origin.username is not None or origin.password is not None
                or origin.path or origin.query or origin.fragment):
            raise ValueError("invalid origin")

        def authority(parts):
            scheme = parts.scheme.lower()
            return scheme, parts.hostname.lower(), (parts.port if parts.port is not None else (443 if scheme == "https" else 80))

        if authority(origin) != authority(target):
            raise ValueError("different origin")
    except (ValueError, AttributeError):
        raise BrowserSessionError("csrf_rejected") from None


def _opaque(value: str) -> bool:
    return isinstance(value, str) and value.isalnum() and value == value.strip() and len(value) >= 8


def _asserts_role(presented: Mapping[str, Any]) -> bool:
    return any(field in presented for field in _ROLE_FIELDS)


def _conflicts(presented: Mapping[str, Any], record: _Record) -> bool:
    if _asserts_role(presented):
        return True
    expected = {
        "user_id": record.principal_id,
        "principal_id": record.principal_id,
        "tenant_id": record.tenant_id,
    }
    for field, actual in expected.items():
        if field not in presented:
            continue
        value = presented[field]
        if not isinstance(value, str) or value != actual:
            return True
    return False


async def _presented_identifiers(request: Any) -> dict[str, Any]:
    presented: dict[str, Any] = {}
    query = getattr(request, "query_params", {}) or {}
    for field in _IDENTITY_FIELDS:
        if field in query:
            presented[field] = query.get(field)
    headers = request.headers
    for header, field in _HEADER_FIELDS:
        if header in headers:
            presented[field] = headers.get(header)
    if request.method.upper() in _UNSAFE_METHODS:
        content_type = str(headers.get("content-type") or "")
        if "application/json" in content_type:
            raw = await request.body()
            if raw:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    raise BrowserSessionError("authentication_failed") from None
                if not isinstance(payload, dict):
                    raise BrowserSessionError("authentication_failed")
                request.state.browser_json = payload
                for field in _IDENTITY_FIELDS:
                    if field in payload:
                        presented[field] = payload[field]
            else:
                request.state.browser_json = {}
    return presented
