# CLAUDE.md

## What This Repo Is

SecID-Client-SDK provides AI-consumable instructions for building SecID clients, plus reference implementations in Python, TypeScript, and Go. The instructions are the primary artifact — the code is verification that they work.

## Key URLs

- **Live API:** `https://secid.cloudsecurityalliance.org/api/v1/resolve?secid={encoded_secid}`
- **MCP Server:** `https://secid.cloudsecurityalliance.org/mcp`
- **Registry repo:** `https://github.com/CloudSecurityAlliance/SecID`
- **Service repo:** `https://github.com/CloudSecurityAlliance/SecID-Service`

## The One Encoding Gotcha

`#` in SecID subpaths must be percent-encoded as `%23` in URL query parameters. This is the #1 failure mode for new clients.

```
CORRECT: /api/v1/resolve?secid=secid:advisory/mitre.org/cve%23CVE-2021-44228
WRONG:   /api/v1/resolve?secid=secid:advisory/mitre.org/cve#CVE-2021-44228
```

## API Summary

One endpoint: `GET /api/v1/resolve?secid={encoded_secid}`

Response envelope: `{secid_query, status, results[], message?}`

Five statuses: `found`, `corrected`, `related`, `not_found`, `error`

Two result types:
- **Resolution:** `{secid, weight, url}` — item resolved to URL(s)
- **Registry:** `{secid, data}` — browsing/discovery info

## File Purposes

| Directory | Purpose | Edit frequency |
|-----------|---------|---------------|
| `skills/build-a-client/` | AI-consumable instructions for building clients | When API changes |
| `python/` | Python reference client (stdlib only) | When API changes |
| `typescript/` | TypeScript reference client (fetch only) | When API changes |
| `go/` | Go reference client (stdlib only) | When API changes |

## Development Commands

```bash
# Python
python python/secid_client.py "secid:advisory/mitre.org/cve#CVE-2021-44228"

# TypeScript
npx tsx typescript/secid-client.ts "secid:advisory/mitre.org/cve#CVE-2021-44228"

# Go
go run go/secid.go "secid:advisory/mitre.org/cve#CVE-2021-44228"

# Smoke test live API
curl "https://secid.cloudsecurityalliance.org/api/v1/resolve?secid=secid:advisory/mitre.org/cve%23CVE-2021-44228"
```

## Design Constraints

1. **No package managers** — reference implementations are single files with zero dependencies
2. **No build systems** — copy a file and run it
3. **Client doesn't parse SecID** — the server has the registry and parsing logic; the client just encodes, sends, and interprets
4. **Instructions are the product** — code is verification that the instructions work
