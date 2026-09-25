# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

SecID-Client-SDK provides AI-consumable instructions for building SecID clients, plus reference implementations in Python, TypeScript, and Go. The instructions are the primary artifact — the code is verification that they work.

`AGENTS.md` carries the same guidance in the vendor-neutral format. Keep the two in sync when either changes.

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

The reference clients encode the *entire* SecID (`quote(safe="")` / `encodeURIComponent` plus `!'()*` / `url.QueryEscape` with `+`→`%20`), not just `#`, and produce byte-identical output — the `encoding_*` fixtures assert the full encoded query. That is deliberate — SPEC.md §8.4 lists many other characters (`@`, `?`, `&`, `%`, space, shell metacharacters) that appear in real identifiers and must survive transport. Don't "optimize" this into a `#`-only replacement.

## API Summary

Primary endpoint: `GET /api/v1/resolve?secid={encoded_secid}`. Two more exist and the clients do not use them: `GET /api/v1/types` (type catalog) and `GET /api/v1/registry.json` (full registry dump, ~4 MB).

Response envelope: `{secid_query, status, results[], message?}`

Five statuses: `found`, `corrected`, `related`, `not_found`, `error`

Two result types:
- **Resolution:** `{secid, weight, url}` — item resolved to URL(s)
- **Registry:** `{secid, data}` — browsing/discovery info

Resolution results may also include optional format metadata: `content_type` (MIME type), `parsability` (`structured` or `scraped`), `schema` (SecID reference to data schema), `parsing_instructions` (SecID reference to parsing guide), `auth` (free-text access description). These are absent when the registry hasn't documented them yet.

Clients must tolerate unknown fields. The server adds them ahead of the SDK — `lang` on resolution results and a top-level `filter` object (returned when a `country` filter is applied) both ship today and are undocumented here.

## Development Commands

Run a client:

```bash
python python/secid_client.py "secid:advisory/mitre.org/cve#CVE-2021-44228"
npx tsx typescript/src/secid-cli.ts "secid:advisory/mitre.org/cve#CVE-2021-44228"   # secid-client.ts is the library; it has no CLI
(cd go && go run ./cmd/secid "secid:advisory/mitre.org/cve#CVE-2021-44228")   # library is package secid; CLI is go/cmd/secid
```

Run the test suites (all three should be green before a PR):

```bash
cd python     && python -m pytest test_secid_client.py -v   # needs pytest only; no install step
cd typescript && npm ci && npm test                         # `pretest` runs tsc; tests execute from dist/
cd go         && go test -v ./...
```

Run a single test:

```bash
cd python     && python -m pytest test_secid_client.py -k found_cve -v
cd typescript && npm run build && node --test --test-name-pattern='found_cve' dist/secid-client.test.js
cd go         && go test -run 'TestFixtures/found_cve' -v
```

Note the TypeScript form: `npm test -- --test-name-pattern=...` does **not** filter (the arg never reaches `node --test`). Call `node` directly.

Resolver conformance suite (CI runs it against the live resolver as a non-blocking job; run it manually against other targets):

```bash
python tests/conformance-harness/python/run.py --target https://secid.cloudsecurityalliance.org
python tests/conformance-harness/python/run.py --target http://localhost:8000 --category resolver/advisory
```

Smoke test the live API:

```bash
curl "https://secid.cloudsecurityalliance.org/api/v1/resolve?secid=secid:advisory/mitre.org/cve%23CVE-2021-44228"
```

## Test Architecture

Two independent fixture suites with different subjects:

| Suite | Fixtures | Tests | Harness |
|-------|----------|-------|---------|
| `tests/fixtures.json` | 35 | **Client** behavior against a per-language mock HTTP server | Python, TypeScript, Go |
| `tests/conformance/fixtures.json` | 10 | **Resolver** behavior against a live or local API | `tests/conformance-harness/python/run.py` (Python only) |

The client suite is the main guard against language drift: all three harnesses read the same JSON and assert the same outcomes, so changing one client's behavior fails its siblings' builds until they follow. **Add behavior to `tests/fixtures.json` first, then make each language pass** — a new fixture needs no harness edits.

Each language also has hand-written tests for hardening the fixture format can't express: URL allowlist, control-character stripping, and hostile bodies served by a raw mock server (mid-body timeouts, non-UTF-8 bytes, unusable base URLs). Counts differ by language; run the suite rather than trusting a number here.

CI (`.github/workflows/test.yml`) runs the client suite across Python 3.9–3.13, Node 18/20/22, and Go 1.21/1.22/1.23 (the floors match `requires-python`, `engines.node`, and `go.mod`). It also runs the conformance suite against the live resolver as a separate job with `continue-on-error`, so a live-API failure is visible without blocking merges. Actions are pinned by commit SHA.

## Client Invariants

Every client — reference or AI-generated — must preserve these, and the hand-written tests enforce them:

- **URL allowlist** — only absolute `http`/`https` URLs with a host, checked by the same hand-written rule in all three languages (not a URL parser; parsers disagree). `resolution_results` drops `javascript:`, `data:`, `file:` and relative URLs, and `best_url` returns the highest-weight *valid* URL, so a hostile top result falls through to the next valid one.
- **10 MB response cap** (`MAX_RESPONSE_BYTES`) — oversized bodies become an error, not an OOM. Matters because `base_url` is user-settable.
- **Terminal sanitization** — strip C0/C1 control characters from server-controlled strings (`url`, `message`, corrected SecID) before printing, or a crafted response injects ANSI escapes.
- **Errors don't crash** — Python and TypeScript return `status="error"`; Go returns `(nil, error)` for transport/parse failures and `(*Response, nil)` with `Status="error"` for server-reported ones. This asymmetry is intentional (idiomatic per language) and the harnesses accept either.

Public surface is deliberately parallel across languages: `resolve`, `lookup`, `best_url`/`bestUrl`/`BestURL`, plus `was_corrected`, `resolution_results`, `registry_results`.

## File Purposes

| Directory | Purpose | Edit frequency |
|-----------|---------|---------------|
| `skills/build-a-client/` | AI-consumable instructions for building clients | When API changes |
| `tests/` | Shared fixtures — edit before touching client code | When behavior changes |
| `python/` | Python reference client (stdlib only) | When API changes |
| `typescript/` | TypeScript reference client (fetch only) | When API changes |
| `go/` | Go reference client (stdlib only) | When API changes |

## Packaging

To be published as `cloudsecurityalliance-secid` (PyPI) and `@cloudsecurityalliance/secid` (npm); neither is on its registry yet, so README "Path 1" gives install-from-git commands. Go is consumed by module path and released with `go/vX.Y.Z` tags (the module is in `go/`). Release steps, including the opt-in `release.yml` workflow, are in `PUBLISHING.md`. Each language has one version source (`__version__`, `package.json` plus a test-enforced `VERSION` literal, and Go `Version`), and the User-Agent is built from it. The distribution name carries the org prefix only where the registry is flat; the import module (`secid_client`) and CLI command (`secid`) stay unprefixed. TypeScript is the only target with a build step (`tsc` → `dist/`) — Python and Go ship the single source file.

## Design Constraints

1. **No package managers** — reference implementations are single files with zero dependencies
2. **No build systems** — copy a file and run it
3. **Client doesn't parse SecID** — the server has the registry and parsing logic; the client just encodes, sends, and interprets
4. **Instructions are the product** — code is verification that the instructions work

## Cross-Repo Coordination

Change order: spec and registry in `SecID` → API behavior in `SecID-Service` → client expectations here. Link the PRs across repos so the rollout order is explicit.

**The MCP server serves its own forked copy of this repo's docs.** `secid://docs/build-a-client` and `secid://docs/prompt-template` are hardcoded string constants in `SecID-Service/src/mcp.ts` (`BUILD_A_CLIENT_DOC`, `PROMPT_TEMPLATE_DOC`), not fetched from `skills/build-a-client/`. They drift silently. When editing anything under `skills/build-a-client/`, check whether the served copy needs the same change and open a companion PR in SecID-Service.
