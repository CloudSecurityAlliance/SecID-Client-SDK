# API Contract

Formal specification of the SecID REST API. This is the authoritative reference for request/response format.

## Endpoint

```
GET https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={encoded_secid}
```

There is one endpoint. All queries go through it.

## Request

### URL Format

```
https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={value}
```

The `{value}` must have `#` encoded as `%23`. All other characters in the SecID string can be sent as-is.

### Encoding Rules

| Character | In SecID String | In Query Parameter |
|-----------|----------------|-------------------|
| `#` | As-is | **Must encode as `%23`** |
| `:` | As-is | As-is (safe in query values) |
| `/` | As-is | As-is (safe in query values) |
| `@` | As-is | As-is |
| `?` | As-is | As-is (part of query string context) |
| Space | N/A (not in SecIDs) | `%20` or `+` |

**Example:**

```
SecID string: secid:advisory/mitre.org/cve#CVE-2021-44228
Query param:  secid=secid:advisory/mitre.org/cve%23CVE-2021-44228
Full URL:     https://secid.cloudsecurityalliance.org/api/v1/resolve?secid=secid:advisory/mitre.org/cve%23CVE-2021-44228
```

### Headers

| Header | Value | Required |
|--------|-------|----------|
| `Accept` | `application/json` | Optional (default) |

No authentication headers. No API keys. No tokens.

### CORS

The API supports CORS. Browser-based clients can call it directly.

## Response

### HTTP Status Codes

| HTTP Code | When |
|-----------|------|
| `200` | All successful processing — including `not_found` and `error` statuses |
| `400` | Completely unparseable request (missing `secid` parameter entirely) |

**Important:** HTTP 200 does NOT mean "found." Check the `status` field in the JSON body.

### Content-Type

```
Content-Type: application/json
```

### Response Schema

```json
{
  "secid_query": "<string>",
  "status": "<string: found|corrected|related|not_found|error>",
  "results": ["<ResultObject>"],
  "message": "<string|null>"
}
```

#### Envelope Fields

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `secid_query` | string | No | Verbatim echo of client input (decoded form) |
| `status` | string | No | One of: `found`, `corrected`, `related`, `not_found`, `error` |
| `results` | array | No | Array of result objects (may be empty `[]`) |
| `message` | string | Yes | Present on `not_found` and `error`; absent/null otherwise |

#### Resolution Result Object

Present when the query resolved to specific URL(s):

```json
{
  "secid": "<string>",
  "weight": "<integer>",
  "url": "<string>"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `secid` | string | Fully-qualified SecID for this result |
| `weight` | integer | Match quality: 100 (authoritative), 80 (high-quality secondary), 50 (indirect/alternative) |
| `url` | string | Resolved URL where the resource can be found |
| `content_type` | string (optional) | MIME type of the resource at the URL (e.g., `application/json`, `text/html`) |
| `parsability` | string (optional) | Whether the resource is `structured` (machine-readable) or `scraped` (requires HTML parsing) |
| `schema` | string (optional) | SecID reference to the data schema for the resource (e.g., `secid:reference/mitre.org/cvelistV5`) |
| `parsing_instructions` | string (optional) | SecID reference to a parsing guide for the resource |
| `auth` | string (optional) | Free-text description of access requirements (e.g., `"API key required"`, `"public"`) |

#### Registry Result Object

Present when the query returned registry browsing data:

```json
{
  "secid": "<string>",
  "data": {
    "official_name": "<string>",
    "common_name": "<string>",
    "description": "<string|null>",
    "urls": [{"type": "<string>", "url": "<string>"}],
    "patterns": ["<string>"],
    "examples": ["<string>"],
    "source_count": "<integer>"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `secid` | string | SecID this data describes |
| `data` | object | Registry metadata (contents vary by query depth) |

The `data` object fields vary depending on what level was queried (type, namespace, source, etc.). All fields within `data` are optional — consume what's present.

## Status Values — Complete Reference

### `found`

The query matched exactly. Results contain resolution or registry data.

```json
{
  "secid_query": "secid:advisory/mitre.org/cve#CVE-2021-44228",
  "status": "found",
  "results": [
    {
      "secid": "secid:advisory/mitre.org/cve#CVE-2021-44228",
      "weight": 100,
      "url": "https://www.cve.org/CVERecord?id=CVE-2021-44228"
    }
  ]
}
```

### `corrected`

The server fixed the input and resolved it. Compare `secid_query` with `results[].secid` to see the correction.

```json
{
  "secid_query": "secid:advisory/redhat.com/RHSA-2026:1234",
  "status": "corrected",
  "results": [
    {
      "secid": "secid:advisory/redhat.com/errata#RHSA-2026:1234",
      "weight": 100,
      "url": "https://access.redhat.com/errata/RHSA-2026:1234"
    }
  ]
}
```

### `related`

Partial match. Results contain registry data about what's available.

```json
{
  "secid_query": "secid:control/nist.gov/csf",
  "status": "related",
  "results": [
    {
      "secid": "secid:control/nist.gov/csf",
      "data": {
        "official_name": "NIST Cybersecurity Framework",
        "description": "Multiple versions available",
        "versions": ["1.1", "2.0"]
      }
    }
  ]
}
```

### `not_found`

Nothing matched. `message` provides guidance.

```json
{
  "secid_query": "secid:advisory/totallyinvented.com/whatever",
  "status": "not_found",
  "results": [],
  "message": "No namespace 'totallyinvented.com' in the advisory registry."
}
```

### `error`

Structurally unparseable. `message` explains what went wrong.

```json
{
  "secid_query": "",
  "status": "error",
  "results": [],
  "message": "Empty query. Provide a SecID string (e.g., secid:advisory/mitre.org/cve#CVE-2024-1234)."
}
```

## SecID String Format (Reference)

```
secid:type/namespace/name[@version][?qualifiers][#subpath[@item_version][?qualifiers]]
```

### Types (fixed list)

| Type | Identifies |
|------|------------|
| `advisory` | Vulnerability publications (CVE, GHSA, vendor advisories) |
| `weakness` | Abstract flaw patterns (CWE, OWASP Top 10) |
| `ttp` | Adversary techniques (ATT&CK, ATLAS, CAPEC) |
| `control` | Security requirements (NIST CSF, ISO 27001) |
| `capability` | Product security features and capabilities |
| `disclosure` | Vulnerability disclosure programs and reporting channels |
| `regulation` | Laws and legal requirements (GDPR, HIPAA) |
| `entity` | Organizations, products, services |
| `reference` | Documents, research, identifier systems (arXiv, DOI, RFC) |

### Common Examples

| SecID | What It Resolves To |
|-------|-------------------|
| `secid:advisory/mitre.org/cve#CVE-2021-44228` | CVE record page |
| `secid:weakness/mitre.org/cwe#CWE-79` | CWE weakness page |
| `secid:ttp/mitre.org/attack#T1059.003` | ATT&CK technique page |
| `secid:control/nist.gov/csf@2.0#PR.AC-1` | NIST CSF control |
| `secid:advisory/CVE-2021-44228` | Cross-source search (all advisory sources) |
| `secid:advisory` | List all advisory namespaces |
