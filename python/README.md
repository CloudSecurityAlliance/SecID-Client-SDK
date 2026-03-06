# secid

Resolve security identifiers to URLs using the [SecID](https://secid.cloudsecurityalliance.org) API.

SecID is a universal grammar for security knowledge — CVEs, CWEs, ATT&CK techniques, NIST controls, and more — maintained by the [Cloud Security Alliance](https://cloudsecurityalliance.org).

**Zero dependencies.** Python 3.9+ stdlib only.

## Install

```bash
pip install secid
```

## CLI

```bash
# Resolve a CVE to its URL
secid "secid:advisory/mitre.org/cve#CVE-2021-44228"

# JSON output
secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"

# Cross-source search (find CVE across all advisory sources)
secid "secid:advisory/CVE-2021-44228"
```

## Library

```python
from secid_client import SecIDClient

client = SecIDClient()

# Get the best URL for a security identifier
url = client.best_url("secid:advisory/mitre.org/cve#CVE-2021-44228")
print(url)  # https://www.cve.org/CVERecord?id=CVE-2021-44228

# Full response with status, results, and guidance
response = client.resolve("secid:advisory/mitre.org/cve#CVE-2021-44228")
print(response.status)           # "found"
print(response.best_url)         # highest-weight URL
print(response.was_corrected)    # True if input was auto-corrected
print(response.resolution_results)  # all URL results, sorted by weight
print(response.registry_results)    # browsing/discovery data

# Cross-source search
response = client.lookup("advisory", "CVE-2021-44228")
```

## SecID Format

```
secid:type/namespace/name[@version]#subpath
```

| Type | Identifies |
|------|-----------|
| `advisory` | Vulnerability publications (CVE, GHSA, vendor advisories) |
| `weakness` | Abstract flaw patterns (CWE, OWASP Top 10) |
| `ttp` | Adversary techniques (ATT&CK, CAPEC) |
| `control` | Security requirements (NIST CSF, ISO 27001) |
| `regulation` | Laws (GDPR, HIPAA) |
| `entity` | Organizations, products, services |
| `reference` | Documents, research (arXiv, DOI, RFC) |

## API

One endpoint: `GET /api/v1/resolve?secid={encoded_secid}`

The `#` character must be encoded as `%23` — the client handles this automatically.

## Links

- [SecID Registry & Spec](https://github.com/CloudSecurityAlliance/SecID)
- [SecID API + MCP Server](https://secid.cloudsecurityalliance.org)
- [Cloud Security Alliance](https://cloudsecurityalliance.org)

## License

Apache 2.0
