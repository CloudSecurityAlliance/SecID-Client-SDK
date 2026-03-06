# SecID Client Test Fixtures

Language-agnostic test suite for all SecID client implementations. One JSON file defines all test cases — each language's test harness reads the same fixtures.

## How It Works

`fixtures.json` contains an array of test cases. Each test specifies:

- **input** — the SecID string and method to call
- **mock_response** — what the mock HTTP server should return
- **expected** — what the client response should look like

Each language's test harness:
1. Reads `fixtures.json`
2. Starts a local mock HTTP server configured with `mock_response`
3. Creates a `SecIDClient` pointed at the mock
4. Calls the method from `input.method`
5. Asserts `expected` fields match

## Running Tests

```bash
# Python (from repo root)
cd python && pip install -e . && python -m pytest test_secid_client.py -v

# TypeScript (from repo root)
cd typescript && npm install && npm test

# Go (from repo root)
cd go && go test -v
```

## Fixture Format

```json
{
  "name": "test_name",
  "description": "What this tests and why",
  "category": "found|corrected|related|not_found|error|encoding|client_error|edge_case",
  "input": {
    "secid": "secid:type/namespace/name#subpath",
    "method": "resolve"
  },
  "mock_response": {
    "http_status": 200,
    "body": { "secid_query": "...", "status": "...", "results": [...], "message": null }
  },
  "expected": {
    "status": "found",
    "best_url": "https://...",
    "was_corrected": false,
    "resolution_result_count": 4,
    "registry_result_count": 0,
    "message": null
  }
}
```

### Mock Response Variants

**Standard** — HTTP status + JSON body:
```json
{ "http_status": 200, "body": { ... } }
```

**Raw body** — non-JSON response (for testing HTML error pages):
```json
{ "http_status": 500, "raw_body": "<html>...</html>", "content_type": "text/html" }
```

**Behavioral** — special mock server behavior:
```json
{ "behavior": "timeout" }
{ "behavior": "oversized_body", "body_size_bytes": 11000000 }
{ "behavior": "connection_refused" }
```

### Expected Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Response status (found, corrected, related, not_found, error) |
| `best_url` | string\|null | Highest-weight URL, or null if none |
| `was_corrected` | boolean | Whether status == "corrected" |
| `resolution_result_count` | integer | Count of results with weight + url |
| `registry_result_count` | integer | Count of results with data |
| `message` | string\|null | Guidance message, or null |
| `raises_error` | boolean | Client should return error (exception or status="error") |
| `error_contains` | string | Substring that should appear in error message |
| `request_url_contains` | string | Substring that should appear in the HTTP request URL |
| `request_url_not_contains` | string | Substring that should NOT appear in the HTTP request URL |

## Adding a Test Case

1. Add an entry to `fixtures.json`
2. Run all three test suites to verify
3. No changes needed to the test harnesses

## Test Categories

| Category | Tests | What's Verified |
|----------|-------|-----------------|
| `found` | Happy-path resolution | best_url selection, weight sorting, result counts |
| `corrected` | Server-corrected input | was_corrected flag, corrected best_url |
| `related` | Partial match / version required | Registry results, no resolution results |
| `not_found` | Unknown namespace/type | Empty results, guidance message |
| `error` | Empty/malformed input | Error status, guidance message |
| `encoding` | Hash, colon, dot in identifiers | %23 encoding, character preservation |
| `client_error` | Timeout, oversized, invalid JSON, 500 | Graceful error handling |
| `edge_case` | Empty results, registry-only, mixed | Client doesn't crash on unusual shapes |

## Cross-Language Error Handling

The three clients handle errors differently:

- **Python** — `resolve()` returns `SecIDResponse(status="error")` for most errors, but may raise `JSONDecodeError` for invalid JSON on HTTP 200
- **TypeScript** — `resolve()` always returns `SecIDResponse` with `status="error"` (never throws)
- **Go** — `Resolve()` returns `(nil, error)` for network/parse failures, `(*Response, nil)` with `Status="error"` for server-reported errors

For `raises_error` tests, each harness checks: **either** an exception/error occurred **or** the response has `status="error"`.
