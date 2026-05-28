# SecID Resolver Conformance Suite

A behavioral contract that every SecID resolver implementation must satisfy.

## What this is

A set of test fixtures (`fixtures.json`) that describe HTTP requests against a SecID resolver and the expected response shape. Run the conformance harness against any resolver — the live Worker, a self-hosted Server-API, a fresh implementation under development — and find out where it diverges from the canonical contract.

The fixtures encode **the spec, made operational**. SPEC.md describes resolver behavior in prose; this directory makes that prose executable.

## Why it lives here

The conformance fixtures live in SecID-Client-SDK rather than in SecID, SecID-Service, or SecID-Server-API for three reasons:

1. **Symmetric.** Both resolver implementations (Worker + Server-API) and client SDKs (this repo) need a shared specification of "what a SecID resolution should look like." Putting it here keeps both halves of the contract in one place.
2. **Extends existing pattern.** This repo already has `tests/fixtures.json` driving the cross-language client tests. The new `tests/conformance/` directory adds a parallel resolver-side fixture set; same idea, different consumer.
3. **Decoupled from any single implementation.** A fixture suite that lives inside SecID-Service would implicitly privilege the Worker's behavior. Here, it's neutral.

## Directory layout

```
tests/
├── fixtures.json              # Existing — client-behavior fixtures (mock-server-driven)
├── conformance/
│   ├── schema.json            # JSON Schema for the fixture format
│   ├── fixtures.json          # The conformance test cases
│   └── README.md              # This file
└── conformance-harness/
    └── python/run.py          # Run-fixtures-against-a-target harness (TS/Go to come)
```

## Running

```bash
# Against the live Worker
python tests/conformance-harness/python/run.py --target https://secid.cloudsecurityalliance.org

# Against a local self-hosted resolver
python tests/conformance-harness/python/run.py --target http://localhost:8000

# Strict mode (full body match in addition to behavioral assertions)
python tests/conformance-harness/python/run.py --target ... --strict

# Filter by category
python tests/conformance-harness/python/run.py --target ... --category resolver/advisory

# Run the 'with_data' variant (tests ?include_data=true mode)
python tests/conformance-harness/python/run.py --target ... --variant with_data
```

Exits 0 if all selected tests pass; 1 with a failure report otherwise.

## Fixture format

See `schema.json` for the formal JSON Schema. The shape:

```json
{
  "name": "resolve-cve-2021-44228",
  "category": "resolver/advisory/cve",
  "description": "...",
  "input": {
    "method": "GET",
    "endpoint": "/api/v1/resolve",
    "query": { "secid": "secid:advisory/mitre.org/cve#CVE-2021-44228" }
  },
  "expected": {
    "http_status": 200,
    "behavioral": {
      "response_status": "found",
      "min_results": 1,
      "must_have_paths": [["results", 0, "url"]],
      "must_not_have_paths": [["results", 0, "data"]],
      "field_assertions": {
        "results[0].url": { "regex": "^https://www\\.cve\\.org/CVERecord\\?id=CVE-2021-44228$" }
      }
    },
    "strict": {
      "body": { "/* optional: full expected response for byte-identical checks */": "..." }
    }
  },
  "variants": {
    "with_data": {
      "input_override": { "query": { "include_data": "true" } },
      "behavioral": { "must_have_paths": [["results", 0, "data"]] }
    }
  }
}
```

### Behavioral vs strict

- **Behavioral** assertions are the **hard contract** — every conforming implementation must pass them. They check semantically meaningful properties: status codes, result counts, URL shapes (via regex), required and forbidden fields.
- **Strict** assertions are **optional pin-downs** — they check the full canonical response shape, byte-for-byte (with key-order-insensitive comparison). Useful for catching subtle drift but easy to over-constrain. Run with `--strict`.

### Variants

A variant is a named modification of a base test — same input shape, slightly different parameters, different expected behavior. The canonical use case is `with_data`, which adds `?include_data=true` to the request and asserts that the response now includes the `data` field on each result.

Implementations that don't yet support a variant's feature should be tested WITHOUT the variant (omit `--variant` for that name). Variants are opt-in by design.

## Adding a fixture

1. Add a new entry to `fixtures.json`'s `tests` array, matching the schema in `schema.json`.
2. Pick a unique kebab-case `name` and an appropriate `category` (use the existing hierarchy where possible).
3. Run the harness against the live Worker to confirm the expected behavior matches reality:
   ```bash
   python tests/conformance-harness/python/run.py --target https://secid.cloudsecurityalliance.org --category your-new-category
   ```
4. Open a PR. The PR's CI will run the suite against the live Worker as a sanity check.

## When fixtures fail

A fixture failure means one of:
- The implementation under test has a bug
- The spec is ambiguous and the fixture encodes one interpretation; another is also reasonable
- The fixture was written wrong

The first is the most common. The other two are worth resolving via SPEC.md updates or fixture revision — don't silently delete failing fixtures.

## Categories

Current categories used in `fixtures.json`:

| Category prefix | What it covers |
|---|---|
| `resolver/advisory/*` | Vulnerability publications, incident reports |
| `resolver/weakness/*` | Abstract weakness patterns (CWE, OWASP) |
| `resolver/ttp/*` | Adversary techniques (ATT&CK, ATLAS, CAPEC) |
| `resolver/control/*` | Security requirements (CCM, ISO, NIST CSF) |
| `resolver/methodology/*` | Formal processes (CVSS, SSVC, etc.) |
| `resolver/discovery/*` | Bare-type listing, namespace listing |
| `resolver/error-paths/*` | Not-found, malformed input, unknown type |
| `discovery/types-endpoint` | GET /api/v1/types |

Add new sub-categories as needed.
