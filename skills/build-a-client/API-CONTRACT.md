# API Contract

Formal specification of the SecID REST API. This is the authoritative reference for request/response format.

## Endpoints

```
GET https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={encoded_secid}
```

`/api/v1/resolve` is the only endpoint a client needs; every lookup goes through it. Two read-only companions exist and the reference clients do not use them:

| Endpoint | Returns |
|----------|---------|
| `GET /api/v1/types` | The type catalog: `{"types": [{"type", "description", "long_description", "namespace_count", "subtypes"}]}` |
| `GET /api/v1/registry.json` | The full registry as one JSON document (about 4 MB) |

## Request

### URL Format

```
https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={value}
```

`{value}` is the **entire SecID string, percent-encoded** with your language's query-component encoder (`urllib.parse.quote(s, safe="")`, `encodeURIComponent`, `url.QueryEscape`). Do not send any part of the SecID unencoded, and do not hand-roll a `#`→`%23` replace.

This matters because real identifiers contain characters that are structural in a query string. Sent as-is, `#` starts a fragment, so the server never sees the subpath. `&` ends the parameter, so `secid:control/cloudsecurityalliance.org/ccm@4.0#A&A-01` reaches the server as `…#A` and comes back `related` instead of `found`. `+` turns into a space. `%` starts an escape.

### Encoding Rules

| Character | Appears in SecIDs? | In the query parameter |
|-----------|-------------------|------------------------|
| `#` | Yes: the subpath separator | `%23` (unencoded, it starts a URL fragment and the subpath is lost) |
| `&` | Yes, e.g. `A&A-01` | `%26` (unencoded, it ends the parameter) |
| `+` | Yes, e.g. `C++` | `%2B` (unencoded, it decodes as a space) |
| `%` | Yes, in some identifiers | `%25` (unencoded, it starts an escape) |
| Space | Yes, in some document and section names | `%20` (the server also accepts `+`) |
| `@` | Yes: the version separator | `%40` |
| `?` | Yes: the qualifier separator | `%3F` |
| `:` `/` | Yes | `%3A` `%2F` (a standard encoder does this, and the server decodes it) |
| Non-ASCII | Yes | UTF-8, then percent-encoded |

**Example:**

```
SecID string: secid:advisory/mitre.org/cve#CVE-2021-44228
Query param:  secid=secid%3Aadvisory%2Fmitre.org%2Fcve%23CVE-2021-44228

SecID string: secid:control/cloudsecurityalliance.org/ccm@4.0#A&A-01
Query param:  secid=secid%3Acontrol%2Fcloudsecurityalliance.org%2Fccm%404.0%23A%26A-01
```

The shorter form `secid=secid:advisory/mitre.org/cve%23CVE-2021-44228` (only `#` encoded) happens to work for that SecID. It breaks as soon as an identifier contains `&`, `+`, `%`, or a space, so do not rely on it.

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
| `200` | Every query the resolver processed, including `not_found` and `error` statuses. A missing or empty `secid` parameter is also HTTP 200, with `status: "error"` and a guidance `message`. |
| `5xx`, others | Outages, proxies, and gateways. The body may be HTML rather than JSON. |

**Important:** HTTP 200 does NOT mean "found." Check the `status` field in the JSON body. Do not rely on a 400 for bad input: the live resolver answers `?secid=` and a request with no parameter at all with HTTP 200. A non-2xx response may still carry a JSON envelope (use its `status`); if it does not, or if any body is not a JSON object, report an error.

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

Clients must ignore fields they do not recognise. The server adds them ahead of this document: `lang` on resolution results, and a top-level `filter` object (`{"country": …, "total_before_filter": …}`) when a `country` query parameter is applied, both ship today.

#### Resolution Result Object

Present when the query resolved to specific URL(s):

```json
{
  "secid": "<string>",
  "weight": "<number>",
  "url": "<string>"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `secid` | string | Fully-qualified SecID for this result |
| `weight` | number | Match quality: 100 (authoritative), 80 (high-quality secondary), 50 (indirect/alternative). Integers today, but accept any JSON number. |
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

Ten types, matching `GET /api/v1/types`:

| Type | Identifies |
|------|------------|
| `advisory` | Vulnerability publications (CVE, GHSA, vendor advisories, incident reports) |
| `weakness` | Abstract flaw patterns (CWE, OWASP Top 10) |
| `ttp` | Adversary techniques (ATT&CK, ATLAS, CAPEC) |
| `control` | Security requirements (NIST CSF, ISO 27001, CCM, CIS Benchmarks) |
| `capability` | Product security features (AWS encryption, CloudTrail, Azure RBAC) |
| `methodology` | Formal processes: scoring, mapping, risk assessment, threat modeling (CVSS, SSVC, STRIDE) |
| `disclosure` | Vulnerability disclosure programs, policies, reporting channels |
| `regulation` | Laws and legal requirements (GDPR, HIPAA, PCI DSS) |
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
