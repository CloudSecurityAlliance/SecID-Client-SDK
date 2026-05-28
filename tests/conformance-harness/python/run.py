#!/usr/bin/env python3
"""SecID conformance harness — Python implementation.

Runs the resolver conformance fixtures in ../../conformance/fixtures.json
against any SecID resolver and reports pass/fail.

Usage:
    python run.py --target https://secid.cloudsecurityalliance.org
    python run.py --target http://localhost:8000 --strict
    python run.py --target ... --category resolver/advisory
    python run.py --target ... --variant with_data

Exits 0 if all fixtures pass; 1 otherwise (with a failure report).

The harness is intentionally stdlib-only (urllib, json, re) so it can run
from any Python 3.9+ environment without dependencies. Equivalent harnesses
in TypeScript and Go will use the same fixture format and assertion logic.

Design notes:
  - 'behavioral' assertions are hard failures — every conforming implementation
    must satisfy them.
  - 'strict' assertions are run only with --strict and produce informational
    pass/fail. Implementations may legitimately differ in cosmetic ways
    (field ordering, optional-field presence) without strict-mode flagging
    them as broken.
  - 'variants' (e.g., 'with_data') are skipped by default; opt in with
    --variant <name>. A target that hasn't implemented the variant's
    feature should skip the variant tests entirely rather than fail.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

DEFAULT_USER_AGENT = "SecID-conformance-harness/1.0"


# ---------------------------------------------------------------------------
# Fixture I/O
# ---------------------------------------------------------------------------


def load_fixtures(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


def make_request(target: str, fixture_input: dict, user_agent: str) -> tuple[int, dict]:
    """Issue the request described by fixture_input against target.

    Returns (http_status, body_json). On non-JSON body or HTTP error, the
    body dict will contain {"_error": "..."}.
    """
    endpoint = fixture_input["endpoint"]
    method = fixture_input["method"]
    query = fixture_input.get("query") or {}
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    headers.update(fixture_input.get("headers") or {})

    qs = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in query.items()
    )
    url = target.rstrip("/") + endpoint
    if qs:
        url += "?" + qs

    body_bytes = None
    if method == "POST" and fixture_input.get("body") is not None:
        body_bytes = json.dumps(fixture_input["body"]).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body_bytes, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        # Capture body of error responses too — error envelopes are part of the contract.
        status = e.code
        raw = e.read().decode("utf-8") if hasattr(e, "read") else ""
    except Exception as e:
        return (-1, {"_error": f"{type(e).__name__}: {e}"})

    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        return (status, {"_error": f"non-JSON body: {e}", "_raw": raw[:500]})
    return (status, body)


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------


def get_path(data: Any, path: list) -> tuple[bool, Any]:
    """Walk data along path. Returns (exists, value).

    Path elements are dict keys (strings) or list indices (ints).
    """
    cur = data
    for p in path:
        if isinstance(p, int):
            if not isinstance(cur, list) or p >= len(cur):
                return (False, None)
            cur = cur[p]
        else:
            if not isinstance(cur, dict) or p not in cur:
                return (False, None)
            cur = cur[p]
    return (True, cur)


# Match "results[0].url" style path strings used in field_assertions.
_PATH_TOKEN = re.compile(r"\[(\d+)\]|([^.\[]+)")


def parse_field_path(s: str) -> list:
    """Parse 'results[0].url' into ['results', 0, 'url']."""
    result = []
    for m in _PATH_TOKEN.finditer(s):
        if m.group(1) is not None:
            result.append(int(m.group(1)))
        else:
            result.append(m.group(2))
    return result


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


def check_behavioral(body: dict, http_status: int, expected: dict) -> list[str]:
    """Run behavioral assertions. Returns a list of failure messages (empty = pass)."""
    failures: list[str] = []
    behavioral = expected.get("behavioral") or {}
    expected_status = expected.get("http_status")

    if expected_status is not None and http_status != expected_status:
        failures.append(f"http_status: expected {expected_status}, got {http_status}")

    if "response_status" in behavioral:
        actual_status = body.get("status")
        if actual_status != behavioral["response_status"]:
            failures.append(f"response_status: expected {behavioral['response_status']!r}, got {actual_status!r}")

    if "min_results" in behavioral or "max_results" in behavioral:
        results = body.get("results")
        if not isinstance(results, list):
            failures.append("results: expected list, missing or wrong type")
        else:
            n = len(results)
            if "min_results" in behavioral and n < behavioral["min_results"]:
                failures.append(f"results count: expected >= {behavioral['min_results']}, got {n}")
            if "max_results" in behavioral and n > behavioral["max_results"]:
                failures.append(f"results count: expected <= {behavioral['max_results']}, got {n}")

    for path in behavioral.get("must_have_paths") or []:
        ok, _ = get_path(body, path)
        if not ok:
            failures.append(f"missing required path: {path}")

    for path in behavioral.get("must_not_have_paths") or []:
        ok, _ = get_path(body, path)
        if ok:
            failures.append(f"forbidden path present: {path}")

    for field_path, assertion in (behavioral.get("field_assertions") or {}).items():
        path = parse_field_path(field_path)
        ok, value = get_path(body, path)
        if not ok:
            failures.append(f"field_assertion {field_path}: field absent")
            continue
        if "equals" in assertion:
            if value != assertion["equals"]:
                failures.append(f"field_assertion {field_path}: expected {assertion['equals']!r}, got {value!r}")
        elif "regex" in assertion:
            if not isinstance(value, str) or not re.match(assertion["regex"], value):
                failures.append(f"field_assertion {field_path}: {value!r} does not match /{assertion['regex']}/")
        elif "contains" in assertion:
            if not isinstance(value, str) or assertion["contains"] not in value:
                failures.append(f"field_assertion {field_path}: {value!r} does not contain {assertion['contains']!r}")
        elif "in" in assertion:
            if value not in assertion["in"]:
                failures.append(f"field_assertion {field_path}: {value!r} not in {assertion['in']!r}")
    return failures


def check_strict(body: dict, expected: dict) -> list[str]:
    """Run strict assertions. Returns failure messages (informational)."""
    strict = expected.get("strict") or {}
    if "body" not in strict:
        return []
    expected_body = strict["body"]
    if not _deep_eq(body, expected_body):
        return [f"strict body mismatch:\n  expected: {json.dumps(expected_body, sort_keys=True)[:300]}\n  actual:   {json.dumps(body, sort_keys=True)[:300]}"]
    return []


def _deep_eq(a: Any, b: Any) -> bool:
    """Key-order-insensitive deep equality."""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_deep_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_deep_eq(x, y) for x, y in zip(a, b))
    return a == b


# ---------------------------------------------------------------------------
# Variant resolution
# ---------------------------------------------------------------------------


def apply_variant(test: dict, variant_name: str) -> Optional[dict]:
    """Merge a variant into a test, producing a synthetic test for that variant.

    Returns None if the variant isn't defined on this test.
    """
    variants = test.get("variants") or {}
    if variant_name not in variants:
        return None
    variant = variants[variant_name]
    merged = dict(test)
    merged["name"] = f"{test['name']}::{variant_name}"

    if "input_override" in variant:
        merged_input = dict(test["input"])
        for k, v in variant["input_override"].items():
            if k == "query" and isinstance(v, dict):
                merged_input["query"] = {**(test["input"].get("query") or {}), **v}
            else:
                merged_input[k] = v
        merged["input"] = merged_input

    merged_expected = dict(test["expected"])
    if "behavioral" in variant:
        base_behav = dict(test["expected"].get("behavioral") or {})
        for k, v in variant["behavioral"].items():
            if k == "must_have_paths":
                base_behav["must_have_paths"] = (base_behav.get("must_have_paths") or []) + v
            elif k == "must_not_have_paths":
                base_behav["must_not_have_paths"] = (base_behav.get("must_not_have_paths") or []) + v
            elif k == "field_assertions":
                base_behav["field_assertions"] = {**(base_behav.get("field_assertions") or {}), **v}
            else:
                base_behav[k] = v
        merged_expected["behavioral"] = base_behav
    if "strict" in variant:
        merged_expected["strict"] = variant["strict"]
    merged["expected"] = merged_expected
    return merged


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_test(target: str, test: dict, *, strict: bool, user_agent: str) -> tuple[bool, list[str]]:
    http_status, body = make_request(target, test["input"], user_agent)
    failures = check_behavioral(body, http_status, test["expected"])
    if strict:
        failures += check_strict(body, test["expected"])
    return (len(failures) == 0, failures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", required=True, help="Base URL of the resolver under test")
    parser.add_argument("--fixtures", default=None, help="Path to fixtures.json (default: ../../conformance/fixtures.json relative to this script)")
    parser.add_argument("--strict", action="store_true", help="Also run strict assertions (full body match)")
    parser.add_argument("--category", default=None, help="Filter tests by category prefix")
    parser.add_argument("--variant", action="append", default=[], help="Run this named variant (e.g., 'with_data'). May be passed multiple times.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--verbose", action="store_true", help="Print response body on failure")
    args = parser.parse_args()

    fixtures_path = Path(args.fixtures) if args.fixtures else Path(__file__).parent.parent.parent / "conformance" / "fixtures.json"
    if not fixtures_path.is_file():
        print(f"ERROR: fixtures not found at {fixtures_path}", file=sys.stderr)
        return 2

    suite = load_fixtures(fixtures_path)
    tests = suite["tests"]
    if args.category:
        tests = [t for t in tests if t["category"].startswith(args.category)]

    # Expand variants
    expanded: list[dict] = []
    for t in tests:
        expanded.append(t)  # base test always included
        for variant_name in args.variant:
            v = apply_variant(t, variant_name)
            if v:
                expanded.append(v)

    print(f"Running {len(expanded)} test(s) against {args.target}")
    if args.strict:
        print("  (strict mode enabled)")
    print()

    passed = failed = 0
    failure_details: list[tuple[str, list[str]]] = []
    for t in expanded:
        ok, failures = run_test(args.target, t, strict=args.strict, user_agent=args.user_agent)
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {t['name']}")
        if ok:
            passed += 1
        else:
            failed += 1
            failure_details.append((t["name"], failures))

    print()
    print(f"Results: {passed} passed, {failed} failed (out of {len(expanded)})")
    if failure_details:
        print()
        print("=== Failures ===")
        for name, failures in failure_details:
            print(f"  {name}")
            for f in failures:
                print(f"    - {f}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
