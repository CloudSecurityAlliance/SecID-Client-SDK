#!/usr/bin/env python3
"""Verify that SecID-Service MCP doc resources stay in sync with skills/build-a-client/.

Can verify either:
1. A local SecID-Service checkout (--local-mcp-ts ../SecID-Service/src/mcp.ts), or
2. A live MCP endpoint (--target https://secid.cloudsecurityalliance.org) via JSON-RPC
   resources/read for secid://docs/build-a-client and secid://docs/prompt-template.

Zero third-party dependencies (stdlib only).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import pathlib
import re
import sys
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / "skills" / "build-a-client"
BUILD_A_CLIENT_PATH = SKILL_DIR / "BUILD-A-CLIENT.md"
PROMPT_TEMPLATE_PATH = SKILL_DIR / "PROMPT-TEMPLATE.md"
MAX_RESPONSE_BYTES = 1_048_576  # 1 MiB cap for MCP HTTP responses


def sha256_exact(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_ts_template(ts_source: str, const_name: str) -> str:
    """Strictly parse a TypeScript template literal constant without executing code.

    Permits only `\\\\`, `\\``, and `\\${` escape sequences (the only escapes
    needed when embedding raw Markdown in a template literal) and rejects any
    unescaped `${...}` interpolation or other JS escape sequence (`\\n`, `\\x`,
    `\\u`, etc.) so local checks can never report a false match.
    """
    header_match = re.search(rf"(?:export\s+)?const\s+{re.escape(const_name)}\s*=\s*`", ts_source)
    if not header_match:
        raise ValueError(f"Could not find template constant {const_name} in TypeScript source")

    i = header_match.end()
    n = len(ts_source)
    out: list[str] = []

    while i < n:
        ch = ts_source[i]
        if ch == "`":
            # End of template literal; verify statement terminator follows
            rest = ts_source[i + 1 : i + 10].lstrip(" \t")
            if not rest.startswith(";"):
                raise ValueError(f"Template constant {const_name} closing backtick not followed by ';'")
            return "".join(out)
        if ch == "$" and i + 1 < n and ts_source[i + 1] == "{":
            raise ValueError(f"Unescaped template interpolation ${{...}} in {const_name}")
        if ch == "\\":
            if i + 1 >= n:
                raise ValueError(f"Trailing backslash at end of {const_name}")
            nxt = ts_source[i + 1]
            if nxt in ("\\", "`"):
                out.append(nxt)
                i += 2
                continue
            if nxt == "$" and i + 2 < n and ts_source[i + 2] == "{":
                out.append("${")
                i += 3
                continue
            raise ValueError(
                f"Unsupported escape sequence \\{nxt!r} in {const_name} "
                f"(escape backslashes as \\\\ so TypeScript preserves literal text)"
            )
        if ch == "\r":
            # Per ECMA-262 §12.8.6, template literals normalize CR and CRLF to LF
            out.append("\n")
            if i + 1 < n and ts_source[i + 1] == "\n":
                i += 2
            else:
                i += 1
            continue
        out.append(ch)
        i += 1

    raise ValueError(f"Unterminated template constant {const_name} in TypeScript source")


def _read_bounded(resp: urllib.request.addinfourl, max_bytes: int = MAX_RESPONSE_BYTES) -> bytes:
    data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"MCP HTTP response exceeded {max_bytes} bytes")
    return data


def fetch_mcp_resource(mcp_url: str, uri: str, req_id: int) -> str:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "secid-mcp-docs-sync-check/1.0",
    }
    init_payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "secid-docs-sync-check", "version": "1.0"},
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(mcp_url, data=init_payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        _ = _read_bounded(resp)

    read_payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "resources/read",
            "params": {"uri": uri},
        }
    ).encode("utf-8")
    req = urllib.request.Request(mcp_url, data=read_payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = _read_bounded(resp).decode("utf-8")

    # Handle either plain JSON or SSE `data: {...}` (matching by JSON-RPC id)
    data_obj = None
    for line in body.splitlines():
        if line.startswith("data: "):
            candidate = json.loads(line[len("data: ") :])
            if isinstance(candidate, dict) and candidate.get("id") == req_id:
                data_obj = candidate
                break
            if isinstance(candidate, dict) and "result" in candidate:
                data_obj = candidate
    if data_obj is None:
        data_obj = json.loads(body)

    return data_obj["result"]["contents"][0]["text"]


def compare_docs(label: str, canonical: str, actual: str) -> bool:
    c_hash = sha256_exact(canonical)
    a_hash = sha256_exact(actual)
    if canonical == actual:
        print(f"OK  {label}: synced (sha256={c_hash[:16]}..., {len(canonical)} chars)")
        return True

    print(
        f"ERR {label}: DRIFT DETECTED!\n"
        f"    canonical sha256={c_hash} ({len(canonical)} chars)\n"
        f"    actual    sha256={a_hash} ({len(actual)} chars)",
        file=sys.stderr,
    )
    diff = list(
        difflib.unified_diff(
            canonical.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"canonical/{label}",
            tofile=f"actual/{label}",
            n=3,
        )
    )
    for line in diff[:60]:
        sys.stderr.write(line)
    if len(diff) > 60:
        sys.stderr.write(f"... ({len(diff) - 60} more diff lines)\n")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-mcp-ts",
        type=pathlib.Path,
        help="Path to SecID-Service/src/mcp.ts",
    )
    parser.add_argument(
        "--target",
        help="Base URL of live SecID service (e.g. https://secid.cloudsecurityalliance.org)",
    )
    args = parser.parse_args()

    canonical_bac = BUILD_A_CLIENT_PATH.read_text(encoding="utf-8")
    canonical_pt = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    default_local = REPO_ROOT.parent / "SecID-Service" / "src" / "mcp.ts"
    local_mcp_ts = args.local_mcp_ts or (default_local if not args.target and default_local.exists() else None)

    if not local_mcp_ts and not args.target:
        parser.error("Provide --target <url> or --local-mcp-ts <path>")

    ok = True
    if local_mcp_ts:
        ts_source = local_mcp_ts.read_text(encoding="utf-8")
        actual_bac = extract_ts_template(ts_source, "BUILD_A_CLIENT_DOC")
        actual_pt = extract_ts_template(ts_source, "PROMPT_TEMPLATE_DOC")
        ok = compare_docs("BUILD-A-CLIENT.md (local mcp.ts)", canonical_bac, actual_bac) and ok
        ok = compare_docs("PROMPT-TEMPLATE.md (local mcp.ts)", canonical_pt, actual_pt) and ok

    if args.target:
        mcp_url = args.target.rstrip("/") + "/mcp"
        actual_bac = fetch_mcp_resource(mcp_url, "secid://docs/build-a-client", 2)
        actual_pt = fetch_mcp_resource(mcp_url, "secid://docs/prompt-template", 3)
        ok = compare_docs("secid://docs/build-a-client (live MCP)", canonical_bac, actual_bac) and ok
        ok = compare_docs("secid://docs/prompt-template (live MCP)", canonical_pt, actual_pt) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
