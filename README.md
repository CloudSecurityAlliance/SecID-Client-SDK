# SecID-Client-SDK

**This is not a traditional SDK.** You do not need a package to use SecID.

A SecID client needs one endpoint, one query parameter, JSON back. The entire client is ~30 lines in any language. The complexity isn't in calling the API — it's in knowing what to do with the results (weights, statuses, version disambiguation). That's better expressed as guidance than as code.

The primary artifact here is **instructions that AI assistants follow to build clients**, plus reference implementations you can copy.

**Philosophy: It's easier to verify AI-generated code than audit someone else's package.**

## Four Paths to Use SecID

### Path 1: Install a Package

> **Not on PyPI or npm yet.** The packages are named `cloudsecurityalliance-secid`
> (PyPI) and `@cloudsecurityalliance/secid` (npm), but neither has been published,
> so `pip install cloudsecurityalliance-secid` and
> `npm install @cloudsecurityalliance/secid` fail today. Until they are, install
> from this repository:

```bash
# Python 3.9+ — pip installs straight from the python/ subdirectory
pip install "git+https://github.com/CloudSecurityAlliance/SecID-Client-SDK#subdirectory=python"

# Node 18+ — npm cannot install from a subdirectory of a git repo, so build a tarball
git clone https://github.com/CloudSecurityAlliance/SecID-Client-SDK
(cd SecID-Client-SDK/typescript && npm ci && npm pack)   # writes cloudsecurityalliance-secid-1.0.0.tgz
npm install ./SecID-Client-SDK/typescript/cloudsecurityalliance-secid-1.0.0.tgz

# Go 1.21+ — Go fetches modules from GitHub directly; no registry involved
go get github.com/CloudSecurityAlliance/SecID-Client-SDK/go@latest
go install github.com/CloudSecurityAlliance/SecID-Client-SDK/go/cmd/secid@latest
```

Or skip installing entirely: each client is a single file (Path 4).

Once published, the registry commands will be:

```bash
pip install cloudsecurityalliance-secid      # Python 3.9+
npm install @cloudsecurityalliance/secid     # Node 18+
```

Then use as library or CLI:

```bash
# CLI (installed by pip, npm, or go install)
secid "secid:advisory/mitre.org/cve#CVE-2021-44228"
```

```python
# Python
from secid_client import SecIDClient
client = SecIDClient()
url = client.best_url("secid:advisory/mitre.org/cve#CVE-2021-44228")
```

```typescript
// TypeScript
import { SecIDClient } from "@cloudsecurityalliance/secid";
const client = new SecIDClient();
const url = await client.bestUrl("secid:advisory/mitre.org/cve#CVE-2021-44228");
```

```go
// Go
import secid "github.com/CloudSecurityAlliance/SecID-Client-SDK/go"
resp, err := secid.NewClient("").Resolve("secid:advisory/mitre.org/cve#CVE-2021-44228")
url := resp.BestURL()
```

> **Package naming (CSA convention).** Where the registry provides a namespace
> (npm scopes, Go module paths), the package keeps a simple name under the org
> namespace — `@cloudsecurityalliance/secid`, `github.com/CloudSecurityAlliance/…`.
> Where the registry is flat (PyPI), the distribution name carries the org prefix:
> `cloudsecurityalliance-secid` (default to the full `cloudsecurityalliance-`
> prefix; fall back to `csa-` only when the name would otherwise be too long or
> the registry constrains length). Import modules and CLI commands stay simple
> (`secid_client`, the `secid` command) regardless.

### Path 2: AI-to-AI (MCP)

Connect your AI assistant to the SecID MCP server. Tools are self-describing. Done.

```
MCP endpoint: https://secid.cloudsecurityalliance.org/mcp
Transport: Streamable HTTP (stateless, no auth)
```

The MCP server IS the SDK for AI-to-AI interaction. It also exposes `secid://docs/build-a-client` and `secid://docs/prompt-template` as resources — an AI can read these to generate an HTTP client in any language.

### Path 3: AI-Generated Client

Give your AI assistant the prompt template. It generates a working client in your language.

1. Copy [`skills/build-a-client/PROMPT-TEMPLATE.md`](skills/build-a-client/PROMPT-TEMPLATE.md)
2. Replace `{LANGUAGE}` with your target language
3. Paste into your AI assistant
4. Get a working single-file client

Everything the AI needs is in that one prompt — no external docs required.

### Path 4: Copy a Reference Implementation

Single file. Zero dependencies. Copy and go.

| Language | File | Runtime |
|----------|------|---------|
| Python | [`python/secid_client.py`](python/secid_client.py) | Python 3.9+ (stdlib only) |
| TypeScript | [`typescript/src/secid-client.ts`](typescript/src/secid-client.ts) (CLI: [`typescript/src/secid-cli.ts`](typescript/src/secid-cli.ts)) | Node 18+ / Deno / Bun (fetch only) |
| Go | [`go/secid.go`](go/secid.go) (CLI: [`go/cmd/secid`](go/cmd/secid/main.go)) | Go 1.21+ (stdlib only) |

All include CLI mode:

```bash
python python/secid_client.py "secid:advisory/mitre.org/cve#CVE-2021-44228"
npx tsx typescript/src/secid-cli.ts "secid:advisory/mitre.org/cve#CVE-2021-44228"
(cd go && go run ./cmd/secid "secid:advisory/mitre.org/cve#CVE-2021-44228")
```

## Why This Approach

SecID is AI-first. The MCP server already handles AI-to-AI integration. For developers who want a client library, the API is simple enough that any AI assistant can generate one correctly — if given the right instructions.

Traditional SDKs are:
- **Published once, stale forever** — API evolves, SDK lags behind
- **One language per package** — maintaining 6+ language SDKs is a full-time job
- **Opaque dependencies** — you inherit someone else's choices about error handling, retries, HTTP clients

AI-generated clients are:
- **Always current** — regenerate from the latest instructions
- **Any language** — including ones that didn't exist when the instructions were written
- **Transparent** — you see every line, you own every line
- **Verifiable** — run it, confirm it works

This is our view of software moving forward: AI builds it, you verify it, you own it.

## Repository Structure

```
SecID-Client-SDK/
├── skills/
│   └── build-a-client/            # AI-consumable instructions
│       ├── BUILD-A-CLIENT.md      # Complete guide for building a client
│       ├── API-CONTRACT.md        # Formal API spec (request, response, encoding)
│       ├── RESULT-HANDLING.md     # Statuses, weights, cross-source, versions
│       └── PROMPT-TEMPLATE.md     # Copy-paste prompt for any language
├── python/                        # PyPI: cloudsecurityalliance-secid (not yet published)
│   ├── secid_client.py            # Python client — stdlib only
│   ├── pyproject.toml             # Package config (hatchling)
│   └── README.md                  # PyPI page
├── typescript/                    # npm: @cloudsecurityalliance/secid (not yet published)
│   ├── src/
│   │   ├── secid-client.ts        # Library exports
│   │   └── secid-cli.ts           # CLI entry point
│   ├── package.json               # Package config (ESM, Node 18+)
│   ├── tsconfig.json              # TypeScript compiler config
│   └── README.md                  # npm page
├── go/                            # module github.com/CloudSecurityAlliance/SecID-Client-SDK/go
│   ├── secid.go                   # Go client (package secid) — stdlib only
│   └── cmd/secid/main.go          # Go CLI
└── tests/
    ├── fixtures.json              # Shared client fixtures (all three languages)
    └── conformance/               # Resolver conformance suite
```

## Quick Start

```bash
# Resolve a CVE using the API directly
curl "https://secid.cloudsecurityalliance.org/api/v1/resolve?secid=secid:advisory/mitre.org/cve%23CVE-2021-44228"

# Python
python python/secid_client.py "secid:advisory/mitre.org/cve#CVE-2021-44228"

# TypeScript
npx tsx typescript/src/secid-cli.ts "secid:advisory/mitre.org/cve#CVE-2021-44228"

# Go
(cd go && go run ./cmd/secid "secid:advisory/mitre.org/cve#CVE-2021-44228")
```

## Related Repositories

| Repo | Purpose |
|------|---------|
| [SecID](https://github.com/CloudSecurityAlliance/SecID) | Specification + registry data |
| [SecID-Service](https://github.com/CloudSecurityAlliance/SecID-Service) | Cloudflare Worker REST API + MCP server |
| **SecID-Client-SDK** (this repo) | Instructions + reference clients |

## Publishing

Maintainers: see [PUBLISHING.md](PUBLISHING.md) for how to publish the npm
(`@cloudsecurityalliance/secid`) and PyPI (`cloudsecurityalliance-secid`)
packages.

## License

Apache 2.0
