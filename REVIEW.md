@AGENTS.md

# Code Review Rules — CloudSecurityAlliance/SecID-Client-SDK

Review instructions for Claude Code Review, GitHub Copilot Code Review, and human/agent reviewers. OpenAI Codex (`codex review` / `codex exec`) reads the matching [`## Code Review Rules`](AGENTS.md#code-review-rules) section in [`AGENTS.md`](AGENTS.md).

Check every PR in `SecID-Client-SDK` against these rules:

## 1. Authority, Provenance, and CI/Release Guardrails

- **Agent attribution:** Agent-authored commits must end with `AI-Agent: <Name>`, and agent PR descriptions/comments must start with `*Agent: <Name> (SecID governing agent)*` (or the contributing agent's role).
- **Governance and gate changes:** Every change to `.github/workflows/test.yml`, `.github/workflows/release.yml`, `.github/workflows/release-ts.yml`, `tests/check_mcp_docs_sync.py`, `AGENTS.md`, or `REVIEW.md` unconditionally requires an independent cross-vendor review and decision record, and must never weaken the `ci-passed` status gate (`test-python`, `test-typescript`, `test-go`, `package-smoke`, `docs-sync`). Widening agent authority requires Kurt's approval first.
- **GitHub Actions supply-chain hygiene:** All third-party GitHub Actions in `.github/workflows/*.yml` must remain pinned by full 40-character commit SHA.
- **Version lockstep & pre-1.0 series (`0.Y.Z`):** All three clients must stay on the `0.Y.Z` pre-1.0 series until Kurt explicitly approves `1.0.0`, and version strings must match across `python/pyproject.toml`, `python/secid_client.py` (`__version__`), `typescript/package.json`, `typescript/src/secid-client.ts` (`VERSION`), and `go/secid.go` (`Version`).

## 2. Client Security Invariants (Python, TypeScript, Go)

Every change to `python/secid_client.py`, `typescript/src/secid-client.ts`, `typescript/src/secid-cli.ts`, `go/secid.go`, `go/cmd/secid/main.go`, or `skills/build-a-client/` must preserve all five client invariants across all three languages:

- **Strict URL scheme & host allowlist:** Only absolute `http://` and `https://` URLs with a non-empty host are accepted (`_is_safe_http_url` / `isSafeHttpUrl` / `isSafeHTTPURL`). `resolution_results` must drop `javascript:`, `data:`, `file:`, and relative URLs, and `best_url` / `bestUrl` / `BestURL` must return the highest-weight *valid* URL.
- **10 MB response size cap (`MAX_RESPONSE_BYTES`):** Enforce the 10 MB response body limit during streaming read so a hostile or misconfigured `base_url` cannot cause an out-of-memory crash.
- **Terminal control-character sanitization:** Strip C0/C1 control characters (`0x00`–`0x1F`, `0x7F`–`0x9F`) from server-controlled strings (`url`, `message`, corrected `secid`) before CLI output so crafted responses cannot inject ANSI terminal escapes.
- **Full SecID percent-encoding:** Percent-encode the entire `secid` query parameter (`#` → `%23`, space → `%20`, `&` → `%26`, `+` → `%2B`, `%` → `%25`, `@` → `%40`, `!'()*`), never a `#`-only replacement.
- **Zero runtime dependencies & non-crashing error handling:** Keep each reference client single-file and stdlib-only. Transport/parse errors return `status="error"` in Python/TypeScript and `(nil, error)` in Go without panicking or raising unhandled exceptions.

## 3. Cross-Language Fixture Parity & MCP Documentation Sync

- **Shared fixture parity (`tests/fixtures.json`):** Add or update shared test cases in `tests/fixtures.json` before changing client behavior, and verify that Python (`pytest`), TypeScript (`npm test`), and Go (`go test ./...`) all pass against the identical fixture file.
- **MCP documentation sync (`skills/build-a-client/`):** `SecID-Service/src/mcp.ts` serves a copy of `skills/build-a-client/README.md` and `PROMPT-TEMPLATE.md`. Any edit under `skills/build-a-client/` must pass `python3 tests/check_mcp_docs_sync.py` and state whether a companion PR in `SecID-Service` is required.
