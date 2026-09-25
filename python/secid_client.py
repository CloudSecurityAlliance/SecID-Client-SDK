#!/usr/bin/env python3
"""SecID client — resolve security identifiers to URLs.

Single file, zero dependencies (stdlib only). Copy and use.

SecID is a universal grammar for security knowledge:
    secid:type/namespace/name[@version]#subpath

API: GET https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={encoded}

IMPORTANT: The # character in SecID strings must be encoded as %23 in the
URL query parameter. This is the #1 failure mode for new clients.

Usage as library:
    from secid_client import SecIDClient
    client = SecIDClient()
    response = client.resolve("secid:advisory/mitre.org/cve#CVE-2021-44228")
    print(response.best_url)

Usage as CLI:
    secid "secid:advisory/mitre.org/cve#CVE-2021-44228"
    secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"
"""

from __future__ import annotations

__version__ = "0.1.0"

import http.client
import json
import math
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE_URL = "https://secid.cloudsecurityalliance.org"
DEFAULT_TIMEOUT = 30  # seconds
MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


@dataclass
class SecIDResponse:
    """Response from the SecID resolve API.

    Attributes:
        secid_query: The query string echoed back (decoded form).
        status: One of: found, corrected, related, not_found, error.
        results: List of result dicts — either resolution or registry type.
            Resolution results have: secid, weight, url, and optional
            content_type, parsability ("structured"/"scraped"), schema
            (SecID reference), parsing_instructions (SecID reference),
            auth (free-text).
        message: Guidance text on not_found/error, None otherwise.
    """

    secid_query: str
    status: str
    results: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None

    @property
    def best_url(self) -> str | None:
        """Highest-weight valid URL from resolution results, or None.

        Only absolute http(s) URLs count (see _validate_url). If the top
        result carries a hostile or malformed URL, the next valid one is
        returned instead of None.
        """
        resolved = self.resolution_results
        return resolved[0]["url"] if resolved else None

    @property
    def was_corrected(self) -> bool:
        """True if the server corrected the input."""
        return self.status == "corrected"

    @property
    def resolution_results(self) -> list[dict[str, Any]]:
        """Only results with a numeric weight and a valid http(s) url, sorted
        by weight descending. Entries with a missing, null, or non-numeric
        weight, or a url that fails _validate_url (javascript:, data:,
        relative, ...), are left out."""
        return sorted(
            [r for r in self.results
             if isinstance(r, dict) and _is_weight(r.get("weight"))
             and _validate_url(r.get("url")) is not None],
            key=lambda r: r["weight"],
            reverse=True,
        )

    @property
    def registry_results(self) -> list[dict[str, Any]]:
        """Only results with data (registry/browsing info)."""
        return [r for r in self.results if isinstance(r, dict) and "data" in r]


def _is_weight(value: Any) -> bool:
    """True for a finite int/float. bool is excluded (it is an int subclass)."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


# The resolver response is untrusted (a hostile, federated, or MITM'd resolver
# is in scope). Only absolute http(s) URLs may be surfaced. The check is done
# by hand rather than with urlparse so that all three reference clients apply
# exactly the same rule; parsers disagree on inputs such as "http:evil",
# "http:///evil" and "http:\\evil" (a WHATWG parser accepts all three).
ALLOWED_URL_SCHEMES = frozenset({"https", "http"})


def _validate_url(url: Any) -> str | None:
    """Return url only if it is an absolute http(s) URL with a host, else None.

    Rules (identical in the Python, TypeScript and Go clients):
      1. a non-empty string with no ASCII control characters or spaces;
      2. begins with "http://" or "https://" (scheme case-insensitive);
      3. the authority (up to the first "/", "?", "#" or backslash), minus
         any "userinfo@", is non-empty and does not start with ":".
    """
    if not isinstance(url, str) or not url:
        return None
    if any(ord(ch) <= 0x20 or ord(ch) == 0x7F for ch in url):
        return None
    scheme, sep, rest = url.partition("://")
    if not sep or scheme.lower() not in ALLOWED_URL_SCHEMES:
        return None
    end = len(rest)
    for delim in "/?#\\":
        i = rest.find(delim)
        if i != -1:
            end = min(end, i)
    host = rest[:end].rpartition("@")[2]
    if not host or host.startswith(":"):
        return None
    return url


def _sanitize_terminal(text: Any) -> str:
    """Strip C0/C1 control chars (incl. ESC) from server-controlled text before
    printing to a terminal — prevents ANSI/escape-sequence injection.

    Accepts any value: a hostile resolver can send a number or object where a
    string is expected, and printing it must not crash the CLI."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return "".join(
        ch for ch in text
        if not (ord(ch) < 0x20 or ord(ch) == 0x7F or 0x80 <= ord(ch) <= 0x9F)
    )


_INVALID = object()

# socket.timeout is an alias of TimeoutError from 3.10; on 3.9 it is a
# separate OSError subclass.
_TIMEOUTS = (TimeoutError, socket.timeout)


def _parse_json(body: bytes) -> Any:
    """Decode a response body as JSON, returning _INVALID on any failure."""
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return _INVALID


def _envelope(data: dict[str, Any], secid: str) -> SecIDResponse:
    """Build a SecIDResponse from an untrusted JSON object, type-checking each
    field. Wrong-typed fields fall back to defaults; non-object results are
    dropped so the result helpers never see them."""
    query = data.get("secid_query")
    status = data.get("status")
    message = data.get("message")
    results = data.get("results")
    return SecIDResponse(
        secid_query=query if isinstance(query, str) else secid,
        status=status if isinstance(status, str) and status else "error",
        results=[r for r in results if isinstance(r, dict)] if isinstance(results, list) else [],
        message=message if isinstance(message, str) else None,
    )


class SecIDClient:
    """HTTP client for the SecID resolve API.

    Args:
        base_url: API base URL. Defaults to the public SecID service.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def resolve(self, secid: str) -> SecIDResponse:
        """Resolve a SecID string to URL(s).

        The # character is automatically encoded as %23 in the query parameter.

        Args:
            secid: Full SecID string, e.g. "secid:advisory/mitre.org/cve#CVE-2021-44228"

        Returns:
            SecIDResponse with status, results, and optional message. Never
            raises for network, HTTP, or response-format problems: those come
            back as status="error" with an explanatory message.
        """
        def error(message: str) -> SecIDResponse:
            return SecIDResponse(secid_query=secid, status="error", message=message)

        try:
            encoded = urllib.parse.quote(secid, safe="")
        except UnicodeEncodeError:  # a lone surrogate cannot be UTF-8 encoded
            return error("SecID is not valid Unicode (unpaired surrogate)")
        url = f"{self.base_url}/api/v1/resolve?secid={encoded}"

        # Every failure mode becomes status="error"; resolve() never raises.
        # OSError covers URLError, socket timeouts, and connection resets;
        # HTTPException covers malformed HTTP (IncompleteRead, BadStatusLine);
        # ValueError covers an unusable base_url ("unknown url type").
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "secid-python-client/1.0",
            })
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as e:
            # Non-2xx: the resolver may still send a JSON envelope.
            try:
                body = e.read(MAX_RESPONSE_BYTES + 1)
            except (OSError, http.client.HTTPException, ValueError) as read_err:
                return error(f"HTTP {e.code}: error reading body: {read_err}")
            data = _parse_json(body)
            if not isinstance(data, dict):
                text = body[:200].decode("utf-8", errors="replace")
                return error(f"HTTP {e.code}: {text}")
            return _envelope(data, secid)
        except urllib.error.URLError as e:
            if isinstance(e.reason, _TIMEOUTS):
                return error(f"Request timeout after {self.timeout}s: {e.reason}")
            return error(f"Connection error: {e.reason}")
        except _TIMEOUTS as e:
            # A timeout while waiting for or reading the response is raised
            # bare, not wrapped in URLError.
            return error(f"Request timeout after {self.timeout}s: {e}")
        except (OSError, http.client.HTTPException) as e:
            return error(f"Connection error: {e}")
        except ValueError as e:
            return error(f"Invalid request URL {url!r}: {e}")

        if len(body) > MAX_RESPONSE_BYTES:
            return error(f"Response exceeds {MAX_RESPONSE_BYTES} byte limit")
        data = _parse_json(body)
        if data is _INVALID:
            return error("Invalid response (not JSON)")
        if not isinstance(data, dict):
            return error(f"Invalid response: expected a JSON object, got {type(data).__name__}")
        return _envelope(data, secid)

    def best_url(self, secid: str) -> str | None:
        """Resolve a SecID and return the highest-weight URL, or None."""
        return self.resolve(secid).best_url

    def lookup(self, type: str, identifier: str) -> SecIDResponse:
        """Cross-source search: find an identifier across all sources of a type.

        Equivalent to resolve(f"secid:{type}/{identifier}").

        Args:
            type: SecID type (advisory, weakness, ttp, control, capability, methodology, disclosure, regulation, entity, reference).
            identifier: The identifier to search for, e.g. "CVE-2021-44228".
        """
        return self.resolve(f"secid:{type}/{identifier}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: secid [--json] <secid>")
        print()
        print("Examples:")
        print('  secid "secid:advisory/mitre.org/cve#CVE-2021-44228"')
        print('  secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"')
        print('  secid "secid:advisory/CVE-2021-44228"')
        sys.exit(0)

    json_mode = "--json" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--json"]
    if not args:
        print("Error: no SecID provided", file=sys.stderr)
        sys.exit(1)

    client = SecIDClient()
    response = client.resolve(args[0])

    if json_mode:
        print(json.dumps({
            "secid_query": response.secid_query,
            "status": response.status,
            "results": response.results,
            "message": response.message,
        }, indent=2))
    elif response.status in ("found", "corrected"):
        url = response.best_url
        if url:
            if response.was_corrected:
                print(f"(corrected to: {_sanitize_terminal(str(response.results[0].get('secid', '')))})", file=sys.stderr)
            print(_sanitize_terminal(url))
        else:
            for r in response.registry_results:
                print(json.dumps(r, indent=2))
    elif response.status == "related":
        for r in response.results:
            print(json.dumps(r, indent=2))
    else:
        msg = response.message or "No results"
        print(f"{response.status}: {_sanitize_terminal(msg)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
