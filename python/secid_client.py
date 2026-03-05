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
    python secid_client.py "secid:advisory/mitre.org/cve#CVE-2021-44228"
    python secid_client.py --json "secid:advisory/mitre.org/cve#CVE-2021-44228"
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE_URL = "https://secid.cloudsecurityalliance.org"


@dataclass
class SecIDResponse:
    """Response from the SecID resolve API.

    Attributes:
        secid_query: The query string echoed back (decoded form).
        status: One of: found, corrected, related, not_found, error.
        results: List of result dicts — either resolution or registry type.
        message: Guidance text on not_found/error, None otherwise.
    """

    secid_query: str
    status: str
    results: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None

    @property
    def best_url(self) -> str | None:
        """Highest-weight URL from resolution results, or None."""
        resolved = self.resolution_results
        return resolved[0]["url"] if resolved else None

    @property
    def was_corrected(self) -> bool:
        """True if the server corrected the input."""
        return self.status == "corrected"

    @property
    def resolution_results(self) -> list[dict[str, Any]]:
        """Only results with weight + url, sorted by weight descending."""
        return sorted(
            [r for r in self.results if "weight" in r and "url" in r],
            key=lambda r: r["weight"],
            reverse=True,
        )

    @property
    def registry_results(self) -> list[dict[str, Any]]:
        """Only results with data (registry/browsing info)."""
        return [r for r in self.results if "data" in r]


class SecIDClient:
    """HTTP client for the SecID resolve API.

    Args:
        base_url: API base URL. Defaults to the public SecID service.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def resolve(self, secid: str) -> SecIDResponse:
        """Resolve a SecID string to URL(s).

        The # character is automatically encoded as %23 in the query parameter.

        Args:
            secid: Full SecID string, e.g. "secid:advisory/mitre.org/cve#CVE-2021-44228"

        Returns:
            SecIDResponse with status, results, and optional message.
        """
        encoded = secid.replace("#", "%23")
        url = f"{self.base_url}/api/v1/resolve?secid={encoded}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "secid-python-client/1.0",
        })
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                return SecIDResponse(
                    secid_query=secid,
                    status="error",
                    message=f"HTTP {e.code}: {body[:200]}",
                )
        except urllib.error.URLError as e:
            return SecIDResponse(
                secid_query=secid,
                status="error",
                message=f"Connection error: {e.reason}",
            )
        return SecIDResponse(
            secid_query=data.get("secid_query", secid),
            status=data.get("status", "error"),
            results=data.get("results", []),
            message=data.get("message"),
        )

    def best_url(self, secid: str) -> str | None:
        """Resolve a SecID and return the highest-weight URL, or None."""
        return self.resolve(secid).best_url

    def lookup(self, type: str, identifier: str) -> SecIDResponse:
        """Cross-source search: find an identifier across all sources of a type.

        Equivalent to resolve(f"secid:{type}/{identifier}").

        Args:
            type: SecID type (advisory, weakness, ttp, control, regulation, entity, reference).
            identifier: The identifier to search for, e.g. "CVE-2021-44228".
        """
        return self.resolve(f"secid:{type}/{identifier}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: secid_client.py [--json] <secid>")
        print()
        print("Examples:")
        print('  secid_client.py "secid:advisory/mitre.org/cve#CVE-2021-44228"')
        print('  secid_client.py --json "secid:advisory/mitre.org/cve#CVE-2021-44228"')
        print('  secid_client.py "secid:advisory/CVE-2021-44228"')
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
                print(f"(corrected to: {response.results[0].get('secid', '')})", file=sys.stderr)
            print(url)
        else:
            for r in response.registry_results:
                print(json.dumps(r, indent=2))
    elif response.status == "related":
        for r in response.results:
            print(json.dumps(r, indent=2))
    else:
        msg = response.message or "No results"
        print(f"{response.status}: {msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
