"""URL-source boundary for Site Magic.

Validation is intentionally strict. The production crawler must additionally pin
the validated address during connection so a later DNS lookup cannot rebind it.
"""

from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from typing import Callable, Iterable, Optional
from urllib.parse import urlsplit, urlunsplit


class UnsafeSiteSourceError(ValueError):
    pass


Resolver = Callable[[str, int], Iterable[tuple]]


def normalize_public_url(url: str, resolver: Optional[Resolver] = None) -> str:
    # Resolve the module attribute at call time so tests and incident tooling
    # can replace DNS deterministically. A function-definition default captured
    # the original socket.getaddrinfo forever and made the URL-source API depend
    # on live DNS even while the documented seam was patched.
    active_resolver = resolver or socket.getaddrinfo
    if len(url) > 2048:
        raise UnsafeSiteSourceError("URL is too long")
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeSiteSourceError("Only public HTTP(S) URLs are accepted")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeSiteSourceError("URL credentials are not accepted")
    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme.lower() == "https" else 80)
    except (UnicodeError, ValueError) as exc:
        raise UnsafeSiteSourceError("Invalid URL host or port") from exc
    if not host or port not in {80, 443}:
        raise UnsafeSiteSourceError("Only ports 80 and 443 are accepted")

    try:
        resolved = list(active_resolver(host, port))
    except OSError as exc:
        raise UnsafeSiteSourceError("URL host could not be resolved") from exc
    if not resolved:
        raise UnsafeSiteSourceError("URL host could not be resolved")
    for result in resolved:
        address = result[4][0]
        try:
            candidate = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeSiteSourceError("URL resolved to an invalid address") from exc
        if not candidate.is_global:
            raise UnsafeSiteSourceError("URL must resolve only to public addresses")

    default_port = (parsed.scheme.lower() == "https" and port == 443) or (
        parsed.scheme.lower() == "http" and port == 80
    )
    netloc = f"[{host}]" if ":" in host else host
    if not default_port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def same_origin(left: str, right: str) -> bool:
    def origin(value: str) -> tuple[str, str, int]:
        parsed = urlsplit(value)
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme.lower() == "https" else 80)
        return parsed.scheme.lower(), (parsed.hostname or "").rstrip(".").lower(), port

    return origin(left) == origin(right)


class _VisibleTextParser(HTMLParser):
    _blocked = frozenset({"script", "style", "iframe", "object", "embed", "template", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in self._blocked:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._blocked and self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth == 0 and data.strip():
            self.parts.append(data.strip())


def extract_hostile_source_text(html: str, max_chars: int = 200_000) -> str:
    parser = _VisibleTextParser()
    parser.feed(html[:1_000_000])
    return "\n".join(parser.parts)[:max_chars]
