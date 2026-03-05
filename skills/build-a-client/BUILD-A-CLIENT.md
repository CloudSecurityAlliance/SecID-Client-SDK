# Build a SecID Client

This document contains everything an AI assistant needs to generate a working SecID client in any language. It is the primary artifact of this repository.

## What You're Building

An HTTP client for a single API endpoint that resolves security knowledge identifiers to URLs. The API is simple; the value is in correctly handling the response.

**Base URL:** `https://secid.cloudsecurityalliance.org`
**Endpoint:** `GET /api/v1/resolve?secid={encoded_secid}`
**Auth:** None. No API keys, no tokens, no headers.

## The One Encoding Gotcha

SecID strings use `#` to separate subpath identifiers:

```
secid:advisory/mitre.org/cve#CVE-2021-44228
```

In a URL query parameter, `#` is the fragment delimiter. You must encode it:

```
CORRECT: /api/v1/resolve?secid=secid:advisory/mitre.org/cve%23CVE-2021-44228
WRONG:   /api/v1/resolve?secid=secid:advisory/mitre.org/cve#CVE-2021-44228
```

**Implementation:** Replace `#` with `%23` in the SecID string before appending it to the URL. Or use your language's URL-encoding, but verify it encodes `#` — some URL encoders treat `#` as a fragment separator and don't encode it.

This is the #1 failure mode for new clients.

## Request Format

```
GET /api/v1/resolve?secid={secid_with_hash_encoded}
Accept: application/json
```

The `secid` parameter value must have `#` encoded as `%23`. All other characters can be sent as-is (the server handles further decoding).

**No request body.** It's a GET with a query parameter. The server returns JSON with `Content-Type: application/json`.

## Response Envelope

Every response — success or failure — has the same shape:

```json
{
  "secid_query": "secid:advisory/mitre.org/cve#CVE-2021-44228",
  "status": "found",
  "results": [...],
  "message": null
}
```

| Field | Type | Always Present | Description |
|-------|------|----------------|-------------|
| `secid_query` | string | Yes | Exactly what the client sent, echoed back (decoded form) |
| `status` | string | Yes | How the query was processed |
| `results` | array | Yes | Zero or more result objects (may be empty) |
| `message` | string | Only on `not_found`/`error` | Human/AI-readable guidance |

## Five Status Values

| Status | Meaning | What to Do |
|--------|---------|------------|
| `found` | Exact match | Use the results directly |
| `corrected` | Server fixed the input and resolved it | Show the corrected SecID; use the results |
| `related` | Partial match; here's what we have | Display registry data; guide user to refine query |
| `not_found` | Nothing matched | Show the `message` field; suggest alternatives |
| `error` | Structurally unparseable input | Show the `message` field; check input format |

**`found` vs `corrected`:** Compare `secid_query` with `results[].secid`. If they differ, the server corrected the input. For example, `secid:advisory/redhat.com/RHSA-2026:1234` gets corrected to `secid:advisory/redhat.com/errata#RHSA-2026:1234` — the user put the identifier as the name instead of the subpath.

**`related`:** The server recognized something (a valid type, a valid namespace) but couldn't fully resolve. Results contain registry data about what's available. This commonly happens when `version_required` sources are queried without a version.

## Two Result Types

Results come in two flavors. Distinguish them by checking for the `weight` field.

### Resolution Result (has `weight` + `url`)

The query resolved to a specific URL:

```json
{
  "secid": "secid:advisory/mitre.org/cve#CVE-2021-44228",
  "weight": 100,
  "url": "https://www.cve.org/CVERecord?id=CVE-2021-44228"
}
```

- **`secid`** — The fully-qualified SecID for this result
- **`weight`** — Match quality: 100 = authoritative primary source, 50 = secondary/indirect
- **`url`** — The resolved URL where this resource lives

### Registry Result (has `data`)

The query returned registry metadata (browsing/discovery):

```json
{
  "secid": "secid:advisory/mitre.org/cve",
  "data": {
    "official_name": "Common Vulnerabilities and Exposures",
    "common_name": "CVE",
    "urls": [
      {"type": "website", "url": "https://cve.org"}
    ],
    "patterns": ["^CVE-\\d{4}-\\d{4,}$"],
    "examples": ["CVE-2024-1234", "CVE-2021-44228"]
  }
}
```

- **`secid`** — The SecID this data describes
- **`data`** — Registry metadata (contents vary by query depth)

**How to distinguish:** If a result has `weight` and `url`, it's a resolution result. If it has `data`, it's a registry result. They never overlap.

## Working with Weights

Multiple results are normal. A single CVE query may return:

```json
{
  "results": [
    {"secid": "secid:advisory/mitre.org/cve#CVE-2021-44228", "weight": 100, "url": "https://www.cve.org/CVERecord?id=CVE-2021-44228"},
    {"secid": "secid:advisory/mitre.org/cve#CVE-2021-44228", "weight": 50, "url": "https://github.com/CVEProject/cvelistV5/blob/main/cves/2021/44xxx/CVE-2021-44228.json"},
    {"secid": "secid:advisory/mitre.org/cve#CVE-2021-44228", "weight": 50, "url": "https://cveawg.mitre.org/api/cve/CVE-2021-44228"}
  ]
}
```

Same resource, three access methods. Weight 100 is the primary human-readable page; weight 50 entries are machine-readable alternatives.

**Sort results by weight descending.** The highest-weight result is the best default. For a "just give me the URL" helper, return `results[0].url` after sorting.

**Weight scale:**
- **100** — Authoritative primary source (this is THE place to go)
- **80** — High-quality secondary source
- **50** — Alternative access method, indirect reference, or secondary mirror

## Cross-Source Search

Omit the namespace to search across all sources of that type:

```
secid:advisory/CVE-2021-44228
```

This returns every advisory source that knows about CVE-2021-44228 — MITRE, NVD, Red Hat, SUSE, etc. Results have different SecIDs showing where each match was found.

This is powerful for "show me everything about this vulnerability" use cases.

## Version Disambiguation

Some sources require a version (OWASP Top 10, NIST CSF). When you query without one:

```
secid:control/nist.gov/csf
```

The response has `status: "related"` with registry data listing available versions. The client should detect this and prompt the user to specify a version:

```
secid:control/nist.gov/csf@2.0
```

Detect version-required: when `status` is `related` and the `data` contains version information, suggest adding `@version` to the query.

## Query Depth

The same endpoint handles different levels of specificity:

| Query | What You Get |
|-------|-------------|
| `secid:advisory/mitre.org/cve#CVE-2021-44228` | Resolution results (URLs) |
| `secid:advisory/mitre.org/cve` | Registry data about CVE as a source |
| `secid:advisory/mitre.org` | List of sources from mitre.org |
| `secid:advisory` | List of all advisory namespaces |

Deeper queries resolve to URLs. Shallower queries browse the registry.

## Implementation Checklist

Your client should:

1. **Encode `#` as `%23`** in the query parameter
2. **Accept any HTTP 200 response** — the status field tells you what happened, not the HTTP code (HTTP 400 only for truly unparseable requests)
3. **Parse the JSON envelope** with all four fields
4. **Handle all 5 status values** — at minimum, distinguish found/corrected (use results) from related/not_found/error (show guidance)
5. **Distinguish result types** — check for `weight`+`url` vs `data`
6. **Sort resolution results by weight descending** — highest weight first
7. **Provide a "best URL" helper** — returns the highest-weight URL or null
8. **Handle empty results** — `results` can be `[]` on not_found/error
9. **Expose the `message` field** — it contains guidance on not_found/error
10. **Support CLI mode** — accept a SecID string as a command-line argument, print the best URL

## Minimal Example (pseudocode)

```
function resolve(secid_string):
    encoded = secid_string.replace("#", "%23")
    url = BASE_URL + "/api/v1/resolve?secid=" + encoded
    response = http_get(url)
    json = parse_json(response.body)
    return {
        query: json.secid_query,
        status: json.status,
        results: json.results,
        message: json.message
    }

function best_url(secid_string):
    result = resolve(secid_string)
    if result.status in ["found", "corrected"]:
        urls = [r for r in result.results if r.weight exists]
        urls.sort_by(weight, descending)
        return urls[0].url if urls else null
    return null
```
