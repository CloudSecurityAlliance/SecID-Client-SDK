# Publishing the SecID client SDKs

How to publish the SecID client libraries to their package registries. Three
languages, three distribution channels:

| Language   | Registry | Package name                       | Notes                          |
|------------|----------|------------------------------------|--------------------------------|
| TypeScript | npm      | `@cloudsecurityalliance/secid`     | Scoped, published **public**   |
| Python     | PyPI     | `cloudsecurityalliance-secid`      | Flat namespace → org prefix    |
| Go         | (none)   | `github.com/CloudSecurityAlliance/SecID-Client-SDK/go` | Consumed by module path; no publish step |

Naming follows the CSA package-naming convention: registries with a namespace
(npm scopes, Go module paths) keep a simple name under the org namespace; flat
registries (PyPI) carry the `cloudsecurityalliance-` prefix on the distribution
name. The import module (`secid_client`) and the CLI command (`secid`) stay
simple regardless of the distribution name.

> **Versions are immutable.** Once a version is published to npm or PyPI it
> cannot be overwritten or re-uploaded — a fix requires a new version number.
> Run the dry-run / check step every time before publishing.

---

## Prerequisites

- **npm:** an account that is a member of the `@cloudsecurityalliance` org/scope
  on npmjs.com, logged in locally (`npm login`). If your account enforces 2FA
  for publishing, npm will prompt for a one-time code during `npm publish`.
- **PyPI:** an account with upload rights, plus an API token. The modern flow
  uses a token (username `__token__`, password `pypi-…`); store it in
  `~/.pypirc` or pass it to `twine`. `twine` itself can be run without a global
  install via `pipx run twine`.

---

## TypeScript → npm (`@cloudsecurityalliance/secid`)

From `typescript/`:

```bash
cd typescript
npm ci                       # clean install of dev deps (tsc, types)
npm test                     # tsc build + node --test (24 tests)
npm publish --dry-run        # inspect the tarball — expect 11 files, NO *.test.*
npm publish                  # real publish (access:public is already in package.json)
```

Notes:
- `publishConfig.access` is set to `public` in `package.json`, so no
  `--access public` flag is needed (scoped packages would otherwise default to
  restricted/private).
- `prepublishOnly` runs `tsc`, so `dist/` is rebuilt automatically on publish.
- The published tarball excludes test files (`files: ["dist/", "!dist/**/*.test.*"]`).
- The `secid` CLI is exposed via the `bin` field — `npx @cloudsecurityalliance/secid …`
  works after publish.

Verify after publishing:

```bash
npm view @cloudsecurityalliance/secid version
```

## Python → PyPI (`cloudsecurityalliance-secid`)

From `python/`:

```bash
cd python
rm -rf dist/ build/ *.egg-info        # clear any stale artifacts (IMPORTANT — see below)
python3 -m build                       # builds sdist + wheel into dist/
pipx run twine check dist/*            # validate metadata + README rendering (expect PASSED)
pipx run twine upload dist/*           # real upload
```

Notes:
- **Always clear `dist/` first.** A stale wheel from an earlier build (e.g. an
  old `secid-0.1.0`) left in `dist/` would get picked up by `twine upload dist/*`
  and either fail or upload the wrong artifact. Alternatively, upload the exact
  files: `twine upload dist/cloudsecurityalliance_secid-1.0.0*`.
- The **wheel** ships only `secid_client.py` (no tests); the **sdist** is the
  full source archive (includes the test file, which is normal — `pip install`
  uses the wheel).
- The import module stays `secid_client` and the console script stays `secid`
  even though the distribution is `cloudsecurityalliance-secid`.
- To test the upload against TestPyPI first:
  `pipx run twine upload --repository testpypi dist/*`.

Verify after publishing:

```bash
pip index versions cloudsecurityalliance-secid    # or: curl https://pypi.org/pypi/cloudsecurityalliance-secid/json
```

A clean end-to-end install check in a throwaway venv:

```bash
python3 -m venv /tmp/secid-check && /tmp/secid-check/bin/pip install cloudsecurityalliance-secid
/tmp/secid-check/bin/secid "secid:advisory/mitre.org/cve#CVE-2021-44228"
rm -rf /tmp/secid-check
```

## Go

No publish step. Consumers use the module path directly:

```bash
go get github.com/CloudSecurityAlliance/SecID-Client-SDK/go
```

A version tag (`git tag vX.Y.Z && git push --tags`) makes a release resolvable
via the Go module proxy, but is not required for `go get` against a branch.

---

## Bumping versions

Keep the three versions in lockstep when releasing a coordinated change:

- npm: `typescript/package.json` → `version`
- PyPI: `python/pyproject.toml` → `version`
- Go: a `vX.Y.Z` git tag

After bumping, re-run the dry-run / check steps above before each publish.

## State as of the first release

At the time this guide was written, neither `@cloudsecurityalliance/secid`
(npm) nor `cloudsecurityalliance-secid` (PyPI) had been published yet — both are
**first publishes** at `1.0.0`, not renames of an existing package, so there is
nothing to deprecate on either registry. Both artifacts have been built and
validated locally (npm dry-run clean at 11 files; `twine check` PASSED; the
wheel installs and the `secid` CLI runs in a clean venv).
