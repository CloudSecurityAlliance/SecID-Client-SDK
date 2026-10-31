# SecID-Client-SDK — Business Case

## Executive summary

`SecID-Client-SDK` provides AI-consumable client-building instructions (`skills/build-a-client/`), zero-dependency single-file reference clients in Python (`python/secid_client.py`), TypeScript (`typescript/src/secid-client.ts`), and Go (`go/secid.go`), and the shared cross-language client fixture suite (`tests/fixtures.json`) and resolver conformance harness (`tests/conformance/fixtures.json` + `tests/conformance-harness/python/run.py`). Instead of forcing developers to audit heavyweight third-party packages, `SecID-Client-SDK` makes integrating SecID trivial across any language — whether by copying a ~320–335-line stdlib-only file, installing a lightweight package (`cloudsecurityalliance-secid`, `@cloudsecurityalliance/secid`, `github.com/CloudSecurityAlliance/SecID-Client-SDK/go`), or handing `PROMPT-TEMPLATE.md` to an AI coding assistant.

## Business benefit categories

- **Adoption & Integration Velocity** — Eliminates the #1 integration failure mode (`#` in SecID subpaths not percent-encoded as `%23`) and provides copy-pasteable, zero-dependency clients and AI prompt templates so any tool or script can resolve SecIDs in minutes.
- **Ecosystem Quality & Conformance Gate** — Houses the canonical cross-language client fixture suite (`tests/fixtures.json`, 35 fixtures) and live resolver conformance suite (`tests/conformance/fixtures.json`), which guard both the client implementations and the server resolvers ([`SecID-Service`](https://github.com/CloudSecurityAlliance/SecID-Service) and [`SecID-Server-API`](https://github.com/CloudSecurityAlliance/SecID-Server-API)) against behavioral drift.
- **Brand & Market Position** — Demonstrates CSA's AI-native engineering philosophy (*"It's easier to verify AI-generated code than audit someone else's package"*), positioning SecID as the easiest security identifier standard to adopt in modern AI-assisted development workflows.

Not directly applicable:

- **Direct Revenue** — Released under Apache-2.0 as free ecosystem enablement.

## Stakeholder value propositions

### CSA Value Proposition
- **CSA programs and engineering teams** get vetted, zero-dependency Python, TypeScript, and Go clients plus a shared conformance harness (`tests/conformance-harness/python/run.py`) that verifies production (`SecID-Service`) and self-hosted (`SecID-Server-API`) resolvers against the specification.
- **Low maintenance footprint:** Because all three reference clients use only language standard libraries (`urllib`, `fetch`, `net/http`) and share a single declarative fixture file (`tests/fixtures.json`), ongoing dependency churn and CVE exposure are near zero.

### Community Value Proposition
- **Developers and security engineers** get four friction-free adoption paths: install a package, connect via MCP, generate a client in any language using `skills/build-a-client/PROMPT-TEMPLATE.md`, or copy a single stdlib-only reference file.
- **Security-hardened client defaults:** Every reference client and AI prompt enforces strict client-side safety invariants against untrusted or self-hosted servers: an explicit `http`/`https` URL scheme allowlist (blocking `javascript:`, `data:`, `file:`), a 10 MB response size cap (`MAX_RESPONSE_BYTES`), C0/C1 terminal control-character stripping to prevent ANSI escape injection, and graceful error handling that never crashes the caller (`status="error"` in Python/TypeScript; `(nil, error)` for transport/parse failures or `Status="error"` for server-reported errors in Go).

### Shared Value Creation
- **Single source of truth for client behavior:** Updating `tests/fixtures.json` and `skills/build-a-client/` keeps human-written packages, copied single-file clients, and AI-generated clients in any language behavioral lockstep.

## AI Enablement

1. **Who becomes more AI-capable because CSA ships this?**
   - **AI coding agents** (Claude Code, Codex, Gemini, Copilot, Cursor) can read `skills/build-a-client/PROMPT-TEMPLATE.md` (`secid://docs/prompt-template`) and `BUILD-A-CLIENT.md` (`secid://docs/build-a-client`) to generate a spec-compliant, security-hardened SecID client in Rust, Java, Ruby, C#, or any other language on demand.
   - **Developers using AI assistants** can embed deterministic SecID resolution into their pipelines without manual API plumbing.
2. **Mechanism:**
   - **Both novel-surface creation and friction removal.** Treating AI instructions (`skills/build-a-client/`) as the primary SDK artifact is a novel AI-native distribution pattern, while the zero-dependency reference clients remove traditional package-management and supply-chain friction.
3. **Counterfactual:**
   - **"Anyone could, but won't / ad-hoc clients break on edge cases."** Without canonical AI prompt templates, encoding rules (`#` → `%23`, full query escaping), and client-side security invariants (URL allowlisting, ANSI stripping, 10 MB caps), every caller writes ad-hoc URL string concatenation that breaks on subpaths/versions or trusts arbitrary server-returned schemes.

## Resources, risks, and operational burden assessment

### Operational burden

*(Note: `SecID-Client-SDK` is a library, prompt-skill, and test-suite repository with no hosted runtime infrastructure; `OPERATIONAL-RESOURCES.md` and `BACKUP-RESOURCES.md` are therefore not applicable.)*

- **Technical operations:** GitHub Actions CI (`.github/workflows/test.yml` running Python 3.9–3.13, Node 18/20/22, Go 1.21–1.23, and live resolver conformance; `.github/workflows/release.yml` for tag-triggered PyPI/npm publishing, while Go modules are served directly from GitHub `go/v*` tags). Zero runtime servers or cloud resources.
- **Human / agent & knowledge operations:** Governed autonomously by the SecID governing agent ([`CSA-Internal-Governance/SecID`](https://github.com/CSA-Internal-Governance/SecID)) with mandatory two-agent cross-vendor code review (`AGENTS.md`). Knowledge operations include maintaining the AI client-building instructions in `skills/build-a-client/` and keeping `SecID-Service`'s MCP resource copies (`secid://docs/build-a-client`, `secid://docs/prompt-template`) synchronized when the API contract evolves.
- **Total ongoing FTE:** < 0.02 human FTE (initial engineering estimate based on stdlib-only clients with zero runtime third-party dependencies to patch and rare `/api/v1/resolve` contract changes; to be validated after 6 months of autonomous governance).
- **Automation / minimization strategy:**
  - All three language test harnesses read `tests/fixtures.json` directly.
  - PyPI and npm package publishing (`release.yml`) is gated by language tags (`python/v*`, `typescript/v*`) and repository variables (`PYPI_PUBLISH_ENABLED`, `NPM_PUBLISH_ENABLED`), and Go releases use `go/v*` tags directly via the Go module proxy, as documented in [`PUBLISHING.md`](PUBLISHING.md).
- **Burden-exceeds-value / sunset trigger:** If a language reference client requires non-stdlib runtime dependencies or exceeds 2 hours/month of maintenance, simplify it back to a minimal single-file stdlib implementation.

### Risks and mitigations

- **Cross-language behavioral or encoding drift →** Mitigated by `tests/fixtures.json` (including `encoding_*` fixtures that assert byte-identical percent-encoding across Python, TypeScript, and Go) run across all supported language versions on every PR.
- **Malicious or compromised custom resolver (`base_url`) returning hostile payloads →** Mitigated by mandatory client invariants enforced across all three languages and `skills/build-a-client/`: `http`/`https` URL allowlist, 10 MB `MAX_RESPONSE_BYTES` cap, C0/C1 control-character stripping, and graceful error handling ("Errors don't crash").
- **Supply-chain risk on published packages →** Mitigated by zero runtime dependencies, SHA-pinned GitHub Actions workflows, and explicit publish gates in `release.yml` ([`PUBLISHING.md`](PUBLISHING.md)).

## Success metrics

Tracked in [`GOALS.md`](GOALS.md):
- **Cross-language parity:** 100% pass rate across Python (3.9–3.13), TypeScript (Node 18/20/22), and Go (1.21–1.23) against `tests/fixtures.json` and hand-written security-hardening tests.
- **Live resolver conformance:** 100% pass rate on `tests/conformance/fixtures.json` against `https://secid.cloudsecurityalliance.org` and `SecID-Server-API`.
- **Zero runtime dependencies:** 0 third-party runtime dependencies in Python, TypeScript, and Go clients.
