# Repository Guidelines

## Project Structure & Module Organization
- `skills/build-a-client/`: canonical AI instructions and prompt templates.
- `tests/fixtures.json`: shared cross-language test fixture source.
- `python/`: packaged Python client (`secid_client.py`) and tests.
- `typescript/`: npm package sources (`src/`), CLI entry, and compiled output target (`dist/`).
- `go/`: single-file Go client and tests.

## Build, Test, and Development Commands
Run from repo root unless noted.

- `cd python && pip install -e . && python -m pytest test_secid_client.py -v`: Python fixture tests.
- `cd typescript && npm ci && npm test`: TypeScript compile + Node test run.
- `cd go && go test -v`: Go fixture tests.
- `python python/secid_client.py "<secid>"`
- `npx tsx typescript/src/secid-client.ts "<secid>"`
- `go run go/secid.go "<secid>"`

## Coding Style & Naming Conventions
- Preserve the zero-runtime-dependency client design per language.
- Python: 4 spaces, `snake_case`, type hints for public interfaces.
- TypeScript: 2 spaces, `camelCase` methods/functions, `PascalCase` types/classes.
- Go: idiomatic naming and `gofmt` formatting.
- Keep public behavior aligned across clients (`resolve`, `lookup`, best URL helpers).

## Testing Guidelines
- Add behavior through `tests/fixtures.json` first; keep language harnesses in sync with fixture schema.
- Keep fixture names stable and descriptive.
- Run Python, TypeScript, and Go suites before opening PRs.
- Include URL-encoding cases (`#` -> `%23`) and error-path cases in fixtures for protocol changes.

## Commit & Pull Request Guidelines
- Prefer small commits scoped to one concern (fixtures, Python, TypeScript, or Go).
- Use imperative commit subjects (`Add ...`, `Fix ...`, `Update ...`).
- PRs should include changed language targets, commands run, and notable fixture additions/updates.

## Cross-Repo Coordination
- Spec and registry changes land in `SecID` first.
- API behavior changes land in `SecID-Service` before client expectations are updated here.
- Link related PRs across repos to keep rollout order explicit.
