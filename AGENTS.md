# Repository Guidelines

## Ecosystem Overview
SecID spans three coordinated repositories:

- `SecID`: specification and authoritative registry data (`registry/**/*.json`).
- `SecID-Service`: Cloudflare Worker exposing REST (`/api/v1/resolve`) and MCP (`/mcp`) over KV-backed registry data.
- `SecID-Client-SDK` (this repo): reference clients and AI client-generation instructions.

When behavior changes, keep contracts aligned across all three: spec/registry shape in `SecID`, resolver behavior in `SecID-Service`, and client/test expectations in this repo.

## Project Structure & Module Organization
- `skills/build-a-client/`: canonical AI instructions (`BUILD-A-CLIENT.md`, contract, prompt template).
- `python/`: single-file client, packaging, and fixture-driven tests.
- `typescript/`: `src/secid-client.ts`, `src/secid-cli.ts`, tests, and packaging/build config.
- `go/`: `secid.go` plus `secid_test.go`.
- `tests/fixtures.json`: shared fixture suite consumed by all language test harnesses.

## Build, Test, and Development Commands
Run from repository root unless noted.

- `cd python && pip install -e . && python -m pytest test_secid_client.py -v`: run Python fixture tests.
- `cd typescript && npm install && npm test`: compile TypeScript and run Node test runner.
- `cd go && go test -v`: run Go fixture tests.
- `python python/secid_client.py "<secid>"`, `npx tsx typescript/secid-client.ts "<secid>"`, `go run go/secid.go "<secid>"`: quick CLI checks.

## Coding Style & Naming Conventions
- Preserve the zero-dependency, single-file client approach in each language.
- Python: 4-space indentation, `snake_case`, typed APIs where practical.
- TypeScript: 2-space indentation, `camelCase` for functions/methods, `PascalCase` for classes/types.
- Go: idiomatic Go formatting (`gofmt`), exported identifiers in `CamelCase`.
- Keep public APIs aligned across languages (`resolve`, `best_url`/`bestUrl`/`BestURL`, `lookup`/`Lookup`).

## Testing Guidelines
- Base new behavior on `tests/fixtures.json`; prefer adding fixtures over one-off, language-only tests.
- Keep fixture `name` values stable and descriptive.
- Before opening a PR, run all three suites: Python, TypeScript, and Go.
- Include URL-encoding assertions (`%23` for `#`) and error-handling expectations.

## Commit & Pull Request Guidelines
- Use short, imperative commit subjects (current history style: `Add ...`, `Fix ...`, `Update ...`).
- Keep commits focused by concern (fixtures, Python client, TypeScript build, etc.).
- PRs should include:
  - what changed and why,
  - affected language(s),
  - test evidence (commands run + outcomes),
  - linked issue(s) when applicable.

## Cross-Repo Change Tips
- For registry/spec updates: change `SecID` first, then `SecID-Service`, then sync fixtures here.
- For API response or status-handling changes: land `SecID-Service` + tests before updating SDK clients.
- Prefer linking related PRs across repos to make review and rollout order explicit.
