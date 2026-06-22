# Prompt Template

Copy everything below the line, replace `{LANGUAGE}` with your language, and paste into your AI assistant. Everything the AI needs is included — no external docs required.

---

## Copy Below This Line

Build me a SecID client library in **{LANGUAGE}**. The entire client is a single file with zero external dependencies (stdlib/built-ins only). Include a CLI mode.

### What SecID Is

SecID is a universal grammar for referencing security knowledge. Format: `secid:type/namespace/name[@version]#subpath`

Examples:
- `secid:advisory/mitre.org/cve#CVE-2021-44228` — CVE record
- `secid:weakness/mitre.org/cwe#CWE-79` — CWE weakness
- `secid:ttp/mitre.org/attack#T1059.003` — ATT&CK technique
- `secid:advisory/CVE-2021-44228` — cross-source search (all advisory sources)

### API Contract

**One endpoint:** `GET https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={encoded_secid}`

**No auth.** No API keys, no tokens, no special headers.

**Critical encoding rule:** Fully query-encode the entire SecID with your language's standard encoder (`urllib.parse.quote(s, safe="")`, `encodeURIComponent`, `url.QueryEscape`). A hand-rolled `#`→`%23` replace is NOT enough — it leaves `&`, `?`, spaces, and other reserved characters unencoded, which corrupts the query. A correct encoder turns `#` into `%23` for you and handles the rest. (Encoding `#` is the historical #1 failure mode; full-encoding closes it and the others at once.)

```
CORRECT: ?secid=secid%3Aadvisory%2Fmitre.org%2Fcve%23CVE-2021-44228
WRONG:   ?secid=secid:advisory/mitre.org/cve#CVE-2021-44228   (# begins the URL fragment — the server never sees it)
```

**Response envelope** (always this shape, HTTP 200 for all processed queries):

```json
{
  "secid_query": "string — echoed input (decoded form)",
  "status": "string — found|corrected|related|not_found|error",
  "results": [
    // Resolution result (resolved to URL):
    {"secid": "string", "weight": 100, "url": "https://..."},
    // OR Registry result (browsing data):
    {"secid": "string", "data": {"official_name": "...", "urls": [...]}}
  ],
  "message": "string|null — guidance on not_found/error, absent otherwise"
}
```

**Five status values:**

| Status | Meaning | Action |
|--------|---------|--------|
| `found` | Exact match | Use results directly |
| `corrected` | Server fixed input, resolved anyway | Use results; optionally show correction |
| `related` | Partial match, here's what's available | Display registry data; may need @version |
| `not_found` | Nothing matched | Show `message` field |
| `error` | Unparseable input | Show `message` field |

**Two result types** (distinguished by fields present):
- Has `weight` + `url` → Resolution result (specific item resolved to URL)
- Has `data` → Registry result (browsing/discovery information)

**Weights:** 100 = authoritative primary, 80 = high-quality secondary, 50 = alternative/indirect. Multiple results are normal — sort by weight descending.

### Required API Surface

```
class SecIDClient:
    constructor(base_url = "https://secid.cloudsecurityalliance.org")

    resolve(secid: string) → SecIDResponse
        # Fully query-encode the secid, call API, return parsed response

    best_url(secid: string) → string | null
        # Resolve, then return highest-weight URL from resolution results
        # Returns null if status is not found/corrected or no resolution results

    lookup(type: string, identifier: string) → SecIDResponse
        # Convenience: resolve("secid:{type}/{identifier}")
        # For cross-source search like lookup("advisory", "CVE-2021-44228")

class SecIDResponse:
    secid_query: string
    status: string  # found|corrected|related|not_found|error
    results: list of result objects
    message: string | null

    property best_url → string | null
        # Highest-weight URL from resolution results, or null.
        # Validate the URL's scheme first (http/https only) — the resolver
        # response is untrusted; reject javascript:/data:/file:/relative.

    property was_corrected → bool
        # True if status is "corrected"

    property resolution_results → list
        # Only results that have weight + url, sorted by weight descending

    property registry_results → list
        # Only results that have data
```

### CLI Mode

When run as a script with a command-line argument:

```
$ python secid_client.py "secid:advisory/mitre.org/cve#CVE-2021-44228"
https://www.cve.org/CVERecord?id=CVE-2021-44228

$ python secid_client.py --json "secid:advisory/mitre.org/cve#CVE-2021-44228"
{full JSON response}

$ python secid_client.py "secid:advisory/totallyinvented.com/whatever"
not_found: No namespace 'totallyinvented.com' in the advisory registry.
```

### Implementation Requirements

1. Single file, zero external dependencies
2. **Full query-encoding of the SecID** via your standard encoder — NOT a `#`→`%23` string replace (CRITICAL — test this; verify it encodes `#`, `&`, and spaces)
3. Handle all 5 status values
4. Distinguish resolution results (weight+url) from registry results (data)
5. Sort resolution results by weight descending
6. `best_url` helper returns highest-weight URL or null
7. CLI mode: print best URL by default, full JSON with --json flag
8. Handle HTTP errors gracefully (network failures, non-200 responses)
9. Include type hints / type annotations
10. Include docstrings explaining the encoding gotcha and status values
11. **Set a 30-second request timeout** — prevents hanging on unresponsive servers
12. **Limit response body to 10 MB** — read at most 10 MB and reject anything larger. Normal responses are 1–5 KB; this protects against memory exhaustion when the client is pointed at a custom base URL
13. **Treat the resolver response as untrusted.** Validate any returned `url`'s scheme in `best_url` (allow `https`/`http` only; reject `javascript:`/`data:`/`file:`/relative). Strip control characters (C0/C1, incl. ESC `0x1B`) from server-controlled strings (`url`, `message`, corrected SecID) before printing them to a terminal — prevents ANSI-escape injection
