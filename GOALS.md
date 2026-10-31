# SecID-Client-SDK — Goals

What `SecID-Client-SDK` achieves as the AI-native client instruction set, multi-language reference library, and conformance suite for [SecID](https://github.com/CloudSecurityAlliance/SecID), and how we measure success.

## Vision / North Star

Make consuming SecID effortless and safe in any programming language or AI workflow — through self-contained AI prompt instructions (`skills/build-a-client/`), zero-dependency single-file reference implementations (Python, TypeScript, Go), and a shared conformance suite that keeps clients and servers in behavioral lockstep.

## CSA Goals (Organization)

- **Objective:** Maintain a canonical, zero-dependency reference client and conformance test suite that validates the SecID API contract across all CSA implementations ([`SecID-Service`](https://github.com/CloudSecurityAlliance/SecID-Service) and [`SecID-Server-API`](https://github.com/CloudSecurityAlliance/SecID-Server-API)).
  - **Success metrics:**
    - 100% pass rate across the CI matrix (`.github/workflows/test.yml`: Python 3.9–3.13, Node 18/20/22, Go 1.21–1.23).
    - 100% pass rate on the resolver conformance suite (`tests/conformance/fixtures.json`) against production `secid.cloudsecurityalliance.org` and `SecID-Server-API`.
- **Objective:** Provide automated, reproducible package publishing for Python (`cloudsecurityalliance-secid` on PyPI), TypeScript (`@cloudsecurityalliance/secid` on npm), and Go (`github.com/CloudSecurityAlliance/SecID-Client-SDK/go`).
  - **Success metrics:**
    - Tag-driven release workflow (`.github/workflows/release.yml`, [`PUBLISHING.md`](PUBLISHING.md)) passes pre-publish test gates and publishes cleanly for every `python/v*` (PyPI, when `PYPI_PUBLISH_ENABLED=true`) and `typescript/v*` (npm, when `NPM_PUBLISH_ENABLED=true`) release tag, and every `go/v*` tag passes CI (`.github/workflows/test.yml`) for direct Go module proxy consumption.

## Community & Ecosystem Goals

- **Objective:** Enable developers and AI coding assistants to build or copy a working, security-hardened SecID client in under 5 minutes with zero third-party runtime dependencies.
  - **Success metrics:**
    - 0 third-party runtime dependencies across `python/secid_client.py`, `typescript/src/secid-client.ts`, and `go/secid.go`.
    - 100% parity between `skills/build-a-client/` documentation (`BUILD-A-CLIENT.md`, `API-CONTRACT.md`, `RESULT-HANDLING.md`, `PROMPT-TEMPLATE.md`) and the live `/api/v1/resolve` response contract.
- **Objective:** Enforce defense-in-depth client safety invariants and encoding fidelity against untrusted or self-hosted server responses.
  - **Success metrics:**
    - 100% enforcement of all four `AGENTS.md` client safety invariants plus encoding fidelity across all reference clients and prompt templates: (1) `http`/`https` URL allowlist on `resolution_results` and `best_url`, (2) 10 MB `MAX_RESPONSE_BYTES` response cap, (3) C0/C1 control-character stripping before terminal output, and (4) graceful error handling ("Errors don't crash": Python/TypeScript return `status="error"`, and Go returns `(nil, error)` for transport/parse failures or `Status="error"` for server-reported errors), alongside byte-identical full SecID percent-encoding (`#` → `%23`, etc.).

## Shared Goals

- **Objective:** Prevent behavioral drift between SecID specifications, servers, and clients through fixture-first development.
  - **Success metrics:** Every client protocol, encoding, or status-handling change lands in `tests/fixtures.json` first and passes identically across Python, TypeScript, and Go, and every server/resolver conformance change lands in `tests/conformance/fixtures.json` (verified via `tests/conformance-harness/python/run.py`).

## Notes

- **How to participate:** Add or update test cases in `tests/fixtures.json` before modifying client code in `python/`, `typescript/`, or `go/`. See [`AGENTS.md`](AGENTS.md) for build and test commands.
- **Related documents:** [`BUSINESS-CASE.md`](BUSINESS-CASE.md), [`PUBLISHING.md`](PUBLISHING.md), [`AGENTS.md`](AGENTS.md), [`skills/build-a-client/BUILD-A-CLIENT.md`](skills/build-a-client/BUILD-A-CLIENT.md).
- **Review triggers:** Revisit goals when PyPI/npm publishing is enabled (`PYPI_PUBLISH_ENABLED`, `NPM_PUBLISH_ENABLED`) or when SecID 2.0 response fields graduate into the client contract.
