# Result Handling Guide

The API is simple. The results require thought. This document covers every scenario you'll encounter when processing SecID responses.

## Quick Decision Tree

```
status == "found" or "corrected"?
  → results have `weight` + `url`?
    → YES: Resolution results. Sort by weight, use URLs.
    → NO (have `data`): Registry browsing results. Display to user.
  → status == "corrected"?
    → YES: Show what was asked vs what was found.

status == "related"?
  → Contains version info? → Prompt user to add @version
  → Otherwise: Show available data, guide user to refine

status == "not_found" or "error"?
  → Show `message` field. Guide user to valid input.
```

## Multiple Results — Same SecID

A single query can return multiple results with the **same** SecID but different URLs and weights:

```json
{
  "status": "found",
  "results": [
    {"secid": "secid:advisory/mitre.org/cve#CVE-2021-44228", "weight": 100, "url": "https://www.cve.org/CVERecord?id=CVE-2021-44228"},
    {"secid": "secid:advisory/mitre.org/cve#CVE-2021-44228", "weight": 50, "url": "https://github.com/CVEProject/cvelistV5/blob/main/cves/2021/44xxx/CVE-2021-44228.json"},
    {"secid": "secid:advisory/mitre.org/cve#CVE-2021-44228", "weight": 50, "url": "https://cveawg.mitre.org/api/cve/CVE-2021-44228"}
  ]
}
```

**What this means:** Same resource, multiple access points. Weight 100 is the primary human-readable page. Weight 50 entries are machine-readable alternatives (GitHub JSON, API endpoint).

**What to do:**
- **"Just give me the URL":** Return the highest-weight result's URL
- **"Show me all options":** Display all results, grouped by weight
- **For programmatic use:** Higher-weight URLs are for humans; lower-weight URLs often point to machine-readable formats (JSON, APIs)

## Multiple Results — Different SecIDs

Cross-source search returns results with **different** SecIDs:

```json
{
  "secid_query": "secid:advisory/CVE-2021-44228",
  "status": "found",
  "results": [
    {"secid": "secid:advisory/mitre.org/cve#CVE-2021-44228", "weight": 100, "url": "https://www.cve.org/CVERecord?id=CVE-2021-44228"},
    {"secid": "secid:advisory/nist.gov/nvd#CVE-2021-44228", "weight": 100, "url": "https://nvd.nist.gov/vuln/detail/CVE-2021-44228"},
    {"secid": "secid:advisory/redhat.com/cve#CVE-2021-44228", "weight": 100, "url": "https://access.redhat.com/security/cve/CVE-2021-44228"},
    {"secid": "secid:advisory/redhat.com/bugzilla#CVE-2021-44228", "weight": 50, "url": "https://bugzilla.redhat.com/show_bug.cgi?id=CVE-2021-44228"}
  ]
}
```

**What this means:** The identifier was found across multiple registries/sources. Each result points to a different organization's page about the same vulnerability.

**What to do:**
- **"Just give me the URL":** Return the highest-weight result (or let the user choose)
- **"Show me everything":** Group by source namespace, show all
- **For security tooling:** All results are useful — different sources have different metadata (NVD has CVSS, Red Hat has patch info)

## Handling `corrected` Status

The server fixed your input. Compare `secid_query` with `results[].secid`:

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

**What happened:** User wrote `RHSA-2026:1234` as the name. The server recognized it belongs under `errata` and corrected to `errata#RHSA-2026:1234`.

**What to do:**
1. Use the results normally (they're valid)
2. Optionally show the user the canonical form: "Did you mean `secid:advisory/redhat.com/errata#RHSA-2026:1234`?"
3. Optionally store the corrected SecID for future use

**Detection:** `response.status === "corrected"` or `response.secid_query !== response.results[0].secid`

## Handling `related` Status

The server found something but couldn't fully resolve:

### Case 1: Version Required

```json
{
  "secid_query": "secid:weakness/owasp.org/top-10",
  "status": "related",
  "results": [
    {
      "secid": "secid:weakness/owasp.org/top-10",
      "data": {
        "official_name": "OWASP Top 10",
        "versions": ["2013", "2017", "2021"]
      }
    }
  ]
}
```

**What happened:** OWASP Top 10 has multiple versions with different content. The server can't resolve without knowing which version.

**What to do:** Prompt the user to specify a version: `secid:weakness/owasp.org/top-10@2021`

**Detection:** `status === "related"` and `data` contains version-related fields (like `versions` array).

### Case 2: Browsing

```json
{
  "secid_query": "secid:advisory/redhat.com/total_junk",
  "status": "related",
  "results": [
    {
      "secid": "secid:advisory/redhat.com",
      "data": {
        "official_name": "Red Hat, Inc.",
        "sources": ["errata", "cve", "bugzilla"]
      }
    }
  ]
}
```

**What happened:** `total_junk` isn't a known source at redhat.com, but the namespace exists. Here's what's available.

**What to do:** Show the available sources. Guide the user to try one: `secid:advisory/redhat.com/errata#...` or `secid:advisory/redhat.com/cve#...`

## Handling `not_found` Status

```json
{
  "secid_query": "secid:advisory/totallyinvented.com/whatever",
  "status": "not_found",
  "results": [],
  "message": "No namespace 'totallyinvented.com' in the advisory registry."
}
```

**What to do:**
1. Show the `message` — it's human/AI-readable guidance
2. `results` is empty; there's nothing to display
3. Suggest: check the type, check the namespace spelling, try cross-source search

## Handling `error` Status

```json
{
  "secid_query": "",
  "status": "error",
  "results": [],
  "message": "Empty query. Provide a SecID string (e.g., secid:advisory/mitre.org/cve#CVE-2024-1234)."
}
```

**What to do:**
1. Show the `message`
2. This means the input was structurally unparseable — not a valid SecID at all
3. Don't retry; fix the input

## Integration Patterns

### Pattern: "Highest weight wins"

For simple integrations that just need a URL:

```
response = resolve(secid)
if response.status in ["found", "corrected"]:
    resolution_results = [r for r in response.results if "weight" in r]
    resolution_results.sort(by: weight, descending)
    return resolution_results[0].url if resolution_results else null
return null
```

### Pattern: "Show all options"

For rich UIs or security dashboards:

```
response = resolve(secid)
if response.status == "found":
    group results by secid
    within each group, sort by weight descending
    display each group with source info
elif response.status == "corrected":
    show "Corrected: {response.secid_query} → {response.results[0].secid}"
    display results as above
elif response.status == "related":
    show registry data from results[].data
    if version info present, prompt for version
elif response.status in ["not_found", "error"]:
    show response.message
```

### Pattern: "Cross-source enrichment"

For security tools that want all available information about an identifier:

```
# Search all advisory sources for a CVE
response = resolve("secid:advisory/CVE-2021-44228")
for result in response.results:
    namespace = extract_namespace(result.secid)  # e.g., "mitre.org", "nist.gov"
    add_to_dashboard(namespace, result.url, result.weight)
```

## Edge Cases

1. **Empty results array with `found` status:** Shouldn't happen, but handle gracefully — treat as `not_found`
2. **Multiple `corrected` results:** The server may correct to multiple possible matches — display all
3. **Mixed result types:** A single response won't mix resolution results (`weight`+`url`) with registry results (`data`) — but code defensively
4. **Very long results arrays:** Cross-source search can return 10+ results. Consider pagination in your UI
5. **`message` field present on `found`/`corrected`:** Shouldn't happen per spec, but ignore it if present — results are authoritative
