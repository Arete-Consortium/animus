"""Governed HTTP client for agent-facing outbound requests.

This client is the single choke-point for the generic ``http_request`` and
``web_search`` execution tools in both Core and Kernel.  Every request is
validated against the centralized egress policy and a set of SSRF invariants
before any bytes are sent, and DNS rebinding is closed by resolving once and
forcing the connection to that IP.

Security invariants (see tests in ``test_security_execution_plane.py``):

* Loopback, RFC1918, link-local, multicast, reserved, and unspecified
  destinations are blocked unless explicitly allowlisted.
* Cloud metadata endpoints (e.g. ``169.254.169.254``) and metadata hostnames
  are blocked.
* Encoded IPv4 literals are normalized to their real address before the
  allowlist is applied.
* Each redirect target is resolved and validated before it is followed.
* Outbound bodies are scanned for credentials by the canonical egress gate.
* Response size, headers, redirect count, duration, and content type are
  capped.
* Secrets and high-entropy tokens are redacted from log/error strings.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from animus_types.egress import EgressDeniedError, is_egress_allowed
from animus_types.secrets import _COMPILED as _SECRET_PATTERNS
from animus_types.sensitivity import Sensitivity

logger = logging.getLogger("animus.network.client")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MAX_BODY_BYTES = 50_000
DEFAULT_MAX_HEADER_BYTES = 16_384
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_DURATION_SECONDS = 60.0
DEFAULT_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "application/json",
        "application/javascript",
        "text/javascript",
        "text/plain",
        "text/html",
        "text/xml",
        "application/xml",
        "application/rss+xml",
        "application/atom+xml",
        "application/octet-stream",
    }
)

# ---------------------------------------------------------------------------
# SSRF blocklists
# ---------------------------------------------------------------------------

_CLOUD_METADATA_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("100.100.100.200/32"),
    ipaddress.ip_network("fd00:ec2::254/128"),
)

_METADATA_HOST_RE: re.Pattern[str] = re.compile(
    r"^(?:metadata(?:-[a-z0-9]+)?\.(?:google\.internal|platform\.instance\.net|oraclecloud\.com)"
    r"|.*\.(?:nip\.io|xip\.io))$",
    re.IGNORECASE,
)

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class SSRFBlockedError(EgressDeniedError):
    """Raised when a destination violates an SSRF invariant."""


@dataclass(frozen=True)
class Response:
    """A governed HTTP response."""

    status: int
    headers: dict[str, str]
    body: str
    url: str


# ---------------------------------------------------------------------------
# Redaction helpers
# ---------------------------------------------------------------------------


def _redact(text: str) -> str:
    """Replace detected credential patterns and high-entropy tokens.

    The goal is to make sure denied-request log lines and error strings
    returned to callers never echo a secret.  We intentionally match the
    same canonical patterns used by ``animus_types.secrets``.
    """
    if not text:
        return text
    for name, pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda _m, _name=name: f"[REDACTED:{_name}]", text)
    return text


def _redact_exception(exc: Exception) -> str:
    """Return a redacted string for an exception, never the raw args."""
    message = " ".join(str(a) for a in exc.args) if exc.args else type(exc).__name__
    return _redact(message)


# ---------------------------------------------------------------------------
# IP / URL validation
# ---------------------------------------------------------------------------


def _decode_ipv4_literal(host: str) -> ipaddress.IPv4Address | None:
    """Parse decimal, hex, octal, and mixed IPv4 literal forms.

    Examples that must be recognized and blocked when they map to a
    disallowed address: ``2130706433``, ``0x7f000001``,
    ``0177.0.0.1``, ``0x7f.0.0.1``.
    """
    host = host.strip()
    if not host:
        return None

    # Pure decimal or hex integer.
    try:
        if host.startswith(("0x", "0X")):
            return ipaddress.IPv4Address(int(host, 16))
        if host.isdigit():
            return ipaddress.IPv4Address(int(host))
    except (ValueError, ipaddress.AddressValueError):
        pass

    # Dotted form (decimal / octal / hex per part).
    parts = host.split(".")
    if len(parts) == 4:
        total = 0
        for part in parts:
            try:
                part = part.strip()
                if part.startswith(("0x", "0X")):
                    value = int(part, 16)
                elif part.startswith("0") and len(part) > 1:
                    value = int(part, 8)
                else:
                    value = int(part)
            except ValueError:
                return None
            if not 0 <= value <= 255:
                return None
            total = (total << 8) | value
        try:
            return ipaddress.IPv4Address(total)
        except ipaddress.AddressValueError:
            return None

    return None


def _ip_is_blocked(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_loopback: bool = False,
    allow_private: bool = False,
) -> str | None:
    """Return a blocking reason or ``None`` if the IP is acceptable."""
    # Loopback is a distinct category from private; Python's ``is_private``
    # also covers 127.0.0.0/8, so we must check it first and short-circuit.
    if ip.is_loopback:
        return None if allow_loopback else "loopback"
    if ip.is_private and not allow_private:
        return "private"
    if ip.is_link_local:
        return "link-local"
    if ip.is_multicast:
        return "multicast"
    if ip.is_reserved:
        return "reserved"
    if ip.is_unspecified:
        return "unspecified"
    for network in _CLOUD_METADATA_NETWORKS:
        if ip in network:
            return "cloud metadata"
    return None


def _is_blocked_host(host: str) -> str | None:
    """Return a blocking reason for the hostname itself, if any."""
    host = host.lower()
    if _METADATA_HOST_RE.match(host):
        return "metadata hostname"
    return None


def _normalize_url(url: str) -> urllib.parse.ParseResult:
    """Parse and normalize a URL, raising ``SSRFBlockedError`` if malformed."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFBlockedError(
            _redact(f"Unsupported URL scheme for governed request: {parsed.scheme}")
        )
    if not parsed.hostname:
        raise SSRFBlockedError("URL is missing a host")
    return parsed


def _validate_destination(
    parsed: urllib.parse.ParseResult,
    *,
    allow_loopback: bool = False,
    allow_private: bool = False,
) -> tuple[str, ipaddress.IPv4Address | ipaddress.IPv6Address | None]:
    """Validate the URL host and return the canonical host plus any decoded IP.

    For encoded IPv4 literals we return the decoded address so the caller can
    decide whether to rewrite the URL or reject it.
    """
    host = parsed.hostname
    assert host is not None  # guarded by _normalize_url

    host_reason = _is_blocked_host(host)
    if host_reason:
        raise SSRFBlockedError(f"SSRF block ({host_reason}): {host}")

    decoded = _decode_ipv4_literal(host)
    if decoded is not None:
        reason = _ip_is_blocked(decoded, allow_loopback=allow_loopback, allow_private=allow_private)
        if reason:
            raise SSRFBlockedError(f"SSRF block ({reason}): {host}")
        return host, decoded

    return host, None


# ---------------------------------------------------------------------------
# DNS pinning / validating resolver
# ---------------------------------------------------------------------------


@contextmanager
def _validating_resolver(
    *,
    allow_loopback: bool = False,
    allow_private: bool = False,
):
    """Temporarily replace ``socket.getaddrinfo`` with an SSRF-aware version.

    Every host resolution is forwarded to the real resolver, then each returned
    IP is checked against the SSRF blocklist.  Only the first allowed result is
    returned, so the subsequent socket connection is forced to that IP and
    cannot be rebound to a different address mid-request.
    """
    original = socket.getaddrinfo

    def _wrapped_getaddrinfo(
        host: str,
        port: Any,
        family: int = 0,
        type: int = 0,  # noqa: A002
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[int, int, int, str, tuple[Any, ...]]]:
        host_reason = _is_blocked_host(host)
        if host_reason:
            raise SSRFBlockedError(f"SSRF block ({host_reason}): {host}")

        try:
            results = original(host, port, family, type, proto, flags)
        except OSError as exc:
            raise SSRFBlockedError(_redact(f"DNS resolution failed for {host}: {exc}")) from exc

        allowed: list[tuple[int, int, int, str, tuple[Any, ...]]] = []
        for af, socktype, pr, canonname, sockaddr in results:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                # Non-IP socket address; skip.
                continue
            reason = _ip_is_blocked(ip, allow_loopback=allow_loopback, allow_private=allow_private)
            if reason:
                logger.debug("SSRF resolver dropped %s -> %s (%s)", host, ip_str, reason)
                continue
            allowed.append((af, socktype, pr, canonname, sockaddr))

        if not allowed:
            raise SSRFBlockedError(f"SSRF block: {host} resolved only to disallowed addresses")

        # Return a single result so urllib connects to exactly this IP.
        return [allowed[0]]

    socket.getaddrinfo = _wrapped_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original


# ---------------------------------------------------------------------------
# Redirect handler with URL-level validation
# ---------------------------------------------------------------------------


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, max_redirections: int = DEFAULT_MAX_REDIRECTS):
        self.max_redirections = max_redirections

    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        # Validate the redirect target at the URL layer; the resolver will
        # re-check it again at the IP layer before any bytes are sent.
        try:
            _normalize_url(newurl)
        except SSRFBlockedError as exc:
            raise SSRFBlockedError(f"SSRF block on redirect to {newurl}: {exc}") from exc
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@contextmanager
def _secure_opener(max_redirects: int = DEFAULT_MAX_REDIRECTS):
    """Install a redirect-capped opener for the duration of the context.

    The default urllib opener is restored in ``finally`` so no global state
    leaks between requests or tests.
    """
    original = urllib.request._opener  # type: ignore[attr-defined]
    opener = urllib.request.build_opener(
        urllib.request.HTTPHandler,
        urllib.request.HTTPSHandler,
        _ValidatingRedirectHandler(max_redirects),
    )
    urllib.request.install_opener(opener)
    try:
        yield
    finally:
        if original is None:
            # install_opener(None) installs the default opener.
            urllib.request.install_opener(
                urllib.request.build_opener(
                    urllib.request.HTTPHandler,
                    urllib.request.HTTPSHandler,
                    urllib.request.HTTPRedirectHandler(),
                )
            )
        else:
            urllib.request.install_opener(original)


# ---------------------------------------------------------------------------
# Response reading with caps
# ---------------------------------------------------------------------------


def _read_response(
    response: urllib.request.addinfourl,
    *,
    max_body_bytes: int,
    max_header_bytes: int,
    max_duration: float,
    allowed_content_types: Iterable[str] | None,
    start_time: float,
) -> Response:
    headers = dict(response.headers)

    header_bytes = sum(len(k) + len(v) + 4 for k, v in headers.items())
    if header_bytes > max_header_bytes:
        raise SSRFBlockedError(
            f"Response header size {header_bytes} exceeds cap {max_header_bytes}"
        )

    content_type = headers.get("Content-Type", "").split(";")[0].strip().lower()
    if allowed_content_types is not None and content_type:
        if content_type not in allowed_content_types:
            raise SSRFBlockedError(
                f"Response content type {content_type!r} is not in the allowed set"
            )

    raw_body = response.read(max_body_bytes + 1)
    elapsed = time.monotonic() - start_time
    if elapsed > max_duration:
        raise SSRFBlockedError(
            f"Response exceeded maximum duration {max_duration}s ({elapsed:.2f}s)"
        )

    truncated = len(raw_body) > max_body_bytes
    if truncated:
        raw_body = raw_body[:max_body_bytes]
        body = raw_body.decode("utf-8", errors="replace") + "\n... [truncated]"
    else:
        body = raw_body.decode("utf-8", errors="replace")

    return Response(
        status=response.status,
        headers=headers,
        body=body,
        url=response.geturl(),
    )


# ---------------------------------------------------------------------------
# Governed client
# ---------------------------------------------------------------------------


class GovernedClient:
    """HTTP client enforcing SSRF guards and the centralized egress policy."""

    @classmethod
    def request(
        cls,
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        body: str | bytes | None = None,
        timeout: float = 30.0,
        sensitivity: Sensitivity | str | None = None,
        content: str | None = None,
        allow_loopback: bool = False,
        allow_private: bool = False,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        max_header_bytes: int = DEFAULT_MAX_HEADER_BYTES,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        max_duration: float = DEFAULT_MAX_DURATION_SECONDS,
        allowed_content_types: Iterable[str] | None = DEFAULT_ALLOWED_CONTENT_TYPES,
    ) -> Response:
        """Execute a governed HTTP request.

        Args:
            url: The full URL.  Only ``http`` and ``https`` are allowed.
            method: HTTP method.
            headers: Optional request headers.
            body: Request body (for POST/PUT/PATCH).  ``str`` is encoded as
                UTF-8.
            timeout: Per-operation socket timeout.
            sensitivity: Sensitivity tier of the outbound data.  Defaults to
                ``Sensitivity.PUBLIC``.
            content: Optional explicit outbound text for the DLP gate.  If
                omitted, the body string is scanned.
            allow_loopback: If ``True``, loopback destinations are permitted.
            allow_private: If ``True``, RFC1918/private destinations are
                permitted.
            max_body_bytes: Maximum response body bytes to read.
            max_header_bytes: Maximum response header bytes to accept.
            max_redirects: Maximum number of redirects to follow.
            max_duration: Wall-clock cap for the entire exchange.
            allowed_content_types: Whitelist of response Content-Types.  ``None``
                disables the check.  A missing Content-Type is always allowed.

        Raises:
            SSRFBlockedError: When an SSRF invariant is violated.
            EgressDeniedError: When the centralized egress policy denies the
                destination or the outbound payload contains a secret.
            urllib.error.HTTPError: For non-2xx responses when the caller has
                opted into raising on HTTP errors (this method does not raise
                by default; see implementation).
        """
        start_time = time.monotonic()
        url = url.strip()
        parsed = _normalize_url(url)

        # Decode/validate the host before any DNS traffic.
        original_host, decoded_ip = _validate_destination(
            parsed,
            allow_loopback=allow_loopback,
            allow_private=allow_private,
        )

        # Resolve the sensitivity tier.
        effective_sensitivity: Sensitivity
        if sensitivity is None:
            effective_sensitivity = Sensitivity.PUBLIC
        elif isinstance(sensitivity, Sensitivity):
            effective_sensitivity = sensitivity
        else:
            try:
                effective_sensitivity = Sensitivity(str(sensitivity).lower())
            except ValueError as exc:
                raise SSRFBlockedError(f"Invalid sensitivity value: {sensitivity}") from exc

        # Content for DLP / egress gate.
        body_bytes: bytes | None = None
        if body is not None:
            body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        outbound_content = content
        if outbound_content is None and body is not None:
            outbound_content = (
                body if isinstance(body, str) else body.decode("utf-8", errors="replace")
            )

        # Centralized egress policy (loopback is always allowed by policy; the
        # allow_loopback/allow_private flags above enforce the SSRF layer).
        if not is_egress_allowed(
            destination=url,
            sensitivity=effective_sensitivity,
            content=outbound_content,
        ):
            raise EgressDeniedError(
                _redact(
                    f"Egress denied by policy for {original_host} "
                    f"with sensitivity {effective_sensitivity.name}"
                )
            )

        # If the host was an encoded IPv4 literal, rewrite the URL to the
        # canonical IP and preserve the original Host header.  Otherwise the
        # validating resolver will pin the real DNS answer.
        final_url = url
        if decoded_ip is not None:
            final_url = urllib.parse.urlunparse(
                parsed._replace(netloc=f"{decoded_ip}:{parsed.port or 80}")
            )

        request_headers = dict(headers) if headers else {}
        if "Host" not in request_headers and decoded_ip is not None:
            request_headers["Host"] = original_host

        req = urllib.request.Request(
            final_url,
            data=body_bytes,
            headers=request_headers,
            method=method.upper(),
        )

        with (
            _validating_resolver(
                allow_loopback=allow_loopback,
                allow_private=allow_private,
            ),
            _secure_opener(max_redirects=max_redirects),
        ):
            try:
                response = urllib.request.urlopen(req, timeout=timeout)
            except urllib.error.HTTPError as exc:
                # For HTTP errors we still want to read the body while applying
                # the same caps, then return a Response object with the error
                # status so callers can decide how to surface it.
                try:
                    resp = _read_response(
                        exc,  # HTTPError is also an addinfourl
                        max_body_bytes=max_body_bytes,
                        max_header_bytes=max_header_bytes,
                        max_duration=max_duration,
                        allowed_content_types=allowed_content_types,
                        start_time=start_time,
                    )
                except Exception as read_exc:
                    logger.debug("Failed to read HTTP error body: %s", _redact_exception(read_exc))
                    resp = Response(
                        status=exc.code,
                        headers=dict(exc.headers or {}),
                        body="",
                        url=exc.url or url,
                    )
                return resp

            return _read_response(
                response,
                max_body_bytes=max_body_bytes,
                max_header_bytes=max_header_bytes,
                max_duration=max_duration,
                allowed_content_types=allowed_content_types,
                start_time=start_time,
            )


# Backwards-compatible module-level helper.
governed_request = GovernedClient.request
