# secid

Resolve security identifiers to URLs using the [SecID](https://secid.cloudsecurityalliance.org) API.

SecID is a universal grammar for security knowledge — CVEs, CWEs, ATT&CK techniques, NIST controls, and more — maintained by the [Cloud Security Alliance](https://cloudsecurityalliance.org).

**Zero runtime dependencies.** Node 18+ (native fetch).

## Install

```bash
npm install secid
```

## CLI

```bash
# Resolve a CVE to its URL
npx secid "secid:advisory/mitre.org/cve#CVE-2021-44228"

# JSON output
npx secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"

# Cross-source search (find CVE across all advisory sources)
npx secid "secid:advisory/CVE-2021-44228"
```

## Library

```typescript
import { SecIDClient } from "secid";

const client = new SecIDClient();

// Get the best URL for a security identifier
const url = await client.bestUrl("secid:advisory/mitre.org/cve#CVE-2021-44228");
console.log(url); // https://www.cve.org/CVERecord?id=CVE-2021-44228

// Full response with status, results, and guidance
const response = await client.resolve("secid:advisory/mitre.org/cve#CVE-2021-44228");
console.log(response.status);            // "found"
console.log(response.bestUrl);           // highest-weight URL
console.log(response.wasCorrected);      // true if input was auto-corrected
console.log(response.resolutionResults); // all URL results, sorted by weight
console.log(response.registryResults);   // browsing/discovery data

// Cross-source search
const results = await client.lookup("advisory", "CVE-2021-44228");

// Capability lookup (product security features)
const cap = await client.resolve("secid:capability/amazon.com/aws/s3#default-encryption");

// Disclosure lookup (who to report vulnerabilities to)
const disc = await client.resolve("secid:disclosure/redhat.com/cna");

// Look up a scoring methodology
const cvss = await client.resolve("secid:methodology/first.org/cvss@4.0");
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
| `capability` | Product security features and capabilities |
| `methodology` | Formal processes for producing security analysis |
| `disclosure` | Vulnerability disclosure programs and reporting channels |
| `regulation` | Laws (GDPR, HIPAA) |
| `entity` | Organizations, products, services |
| `reference` | Documents, research (arXiv, DOI, RFC) |

## API

One endpoint: `GET /api/v1/resolve?secid={encoded_secid}`

The `#` character must be encoded as `%23` — the client handles this automatically.

Resolution results may include optional format metadata fields: `content_type`, `parsability`, `schema`, `parsing_instructions`, and `auth`. These describe the data format at the resolved URL and are present only when the registry has documented them.

## Links

- [SecID Registry & Spec](https://github.com/CloudSecurityAlliance/SecID)
- [SecID API + MCP Server](https://secid.cloudsecurityalliance.org)
- [Cloud Security Alliance](https://cloudsecurityalliance.org)

## License

Apache 2.0
