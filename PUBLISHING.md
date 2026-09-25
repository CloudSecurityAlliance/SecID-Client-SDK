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
npm test                     # tsc build + node --test
npm publish --dry-run        # inspect the tarball — expect 7 files: LICENSE, README.md,
                             # package.json, dist/secid-{client,cli}.{js,d.ts}; no tests, no maps
npm publish                  # real publish (access:public is already in package.json)
```

Notes:
- `publishConfig.access` is set to `public` in `package.json`, so no
  `--access public` flag is needed (scoped packages would otherwise default to
  restricted/private).
- `prepack` runs `tsc`, so `dist/` is rebuilt automatically on both `npm pack`
  and `npm publish`. (It used to be `prepublishOnly`, which `npm pack` skips,
  so a locally packed tarball shipped without `dist/`.)
- Source maps and declaration maps are off (`tsconfig.json`): they pointed at
  `src/`, which the package does not ship.
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

No registry upload. Consumers fetch the module straight from GitHub through the
Go module proxy:

```bash
go get github.com/CloudSecurityAlliance/SecID-Client-SDK/go@v1.0.0
go install github.com/CloudSecurityAlliance/SecID-Client-SDK/go/cmd/secid@v1.0.0
```

**The module is in the `go/` subdirectory, so its tags must be prefixed with
`go/`.** Go maps a module at `<repo>/go` to tags named `go/vX.Y.Z`. A plain
`vX.Y.Z` tag on the repository root is ignored for this module — `go get
…/go@v1.0.0` would fail to find it.

```bash
git checkout main && git pull
cd go && go test ./... && cd ..
git tag -a go/v1.0.0 -m "Go client v1.0.0"
git push origin go/v1.0.0
```

Verify the proxy has picked it up (may take a minute):

```bash
GOPROXY=https://proxy.golang.org go list -m github.com/CloudSecurityAlliance/SecID-Client-SDK/go@v1.0.0
```

Without any tag, `go get …/go@main` still works, but consumers get a
pseudo-version (`v0.0.0-2026…-abcdef`) rather than `v1.0.0`.

Notes:
- The library is `package secid` (importable); the CLI is `go/cmd/secid`
  (`package main`). A `package main` library cannot be imported, which is why
  they are split.
- Go tags are immutable in practice: the module proxy and checksum database
  cache the first content they see for a tag. Never move or re-push a tag —
  cut a new patch version instead.

---

## Bumping versions

Each language has one place that defines its version; the User-Agent header is
derived from it. Keep the three in lockstep for a coordinated release:

| Language | Edit this | Also follows it |
|---|---|---|
| Python | `__version__` in `python/secid_client.py` | `pyproject.toml` reads it (hatch dynamic version); UA `secid-python-client/<version>` |
| TypeScript | `version` in `typescript/package.json` **and** `VERSION` in `typescript/src/secid-client.ts` | A test fails if the two differ. The literal stays in the `.ts` file so it works when copied alone. UA `secid-typescript-client/<version>` |
| Go | `Version` in `go/secid.go`, then tag `go/vX.Y.Z` | UA `secid-go-client/<version>` |

After bumping, re-run the dry-run / check steps above before each publish.

## State as of the first release

**Nothing has been published yet** (checked 2026-09-24):

- PyPI `cloudsecurityalliance-secid`: 404, name unclaimed.
- npm `@cloudsecurityalliance/secid`: 404. No packages exist under the
  `@cloudsecurityalliance` scope, so first confirm that the npm org exists and
  that your account can publish to it.
- Go: no `go/v*` tag exists. The repository does have a root `v1.0.0` tag, but
  Go ignores it for the `go/` module (see the Go section).

All three are first releases at `1.0.0`, not renames, so there is nothing to
deprecate. Local checks (2026-09-24): `python -m build` plus `twine check
--strict` PASSED; the wheel holds only `secid_client.py` and installs a working
`secid` CLI in a clean venv. `npm pack --dry-run` lists 7 files; a packed
tarball installs into a scratch project, where both `npx secid` and `import`
work. A scratch Go module imports `…/go` through a `replace` directive and
builds.

Until the registries are populated, the README tells users to install from git.
Once you publish, update README "Path 1" to put the registry commands first.

---

## Automated publishing (proposed)

`.github/workflows/release.yml` publishes from GitHub Actions when you push a
release tag by hand:

| Tag | Publishes | Auth |
|---|---|---|
| `python/vX.Y.Z` | PyPI `cloudsecurityalliance-secid` | **Trusted publishing** (OIDC). No token is stored anywhere. |
| `typescript/vX.Y.Z` | npm `@cloudsecurityalliance/secid` | `NPM_TOKEN` secret, published with `--provenance` |
| `go/vX.Y.Z` | nothing (the tag is the Go release) | — |

Both jobs first check that the tag matches the version in code, then run the
tests, then publish. **The workflow does nothing until you opt in:** each
publish job is skipped unless a repository variable is set to `true`, so a tag
pushed before setup is harmless.

### One-time setup: PyPI (trusted publishing)

1. Sign in at <https://pypi.org> with the account that should own the project.
2. Go to <https://pypi.org/manage/account/publishing/> and, under "Add a new
   pending publisher" (this reserves the name on first use), enter:
   - PyPI project name: `cloudsecurityalliance-secid`
   - Owner: `CloudSecurityAlliance`
   - Repository name: `SecID-Client-SDK`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. On GitHub, create the environment: Settings → Environments → New
   environment → `pypi`. Recommended: add yourself as a required reviewer, so
   every upload waits for your approval, and restrict deployment tags to
   `python/v*`.
4. Settings → Secrets and variables → Actions → Variables → New repository
   variable: `PYPI_PUBLISH_ENABLED` = `true`.

### One-time setup: npm (token plus provenance)

1. Confirm the `cloudsecurityalliance` org exists on npmjs.com and that your
   account can publish to it (create the org if it does not exist).
2. Create a **granular access token** (npmjs.com → Access Tokens → Generate New
   Token → Granular) with read-and-write permission scoped to the
   `@cloudsecurityalliance` scope (or to the package, once it exists) and a
   short expiry. If your org requires 2FA for publishing, the token must be
   allowed to bypass it for automation, or the CI publish is rejected.
3. On GitHub, create the environment `npm` (as above; add yourself as a
   required reviewer and restrict tags to `typescript/v*`), then add the token
   as an **environment secret** named `NPM_TOKEN`.
4. Add the repository variable `NPM_PUBLISH_ENABLED` = `true`.

`--provenance` attaches a signed statement to the npm package that links it
to this repository, commit, and workflow run. It needs the `id-token: write`
permission, which the job already requests.

After the first publish you can drop the token: npm also supports trusted
publishing (OIDC) under the package's Settings → Trusted Publisher, with
`release.yml` and environment `npm`. It can only be configured once the package
exists. It needs npm CLI 11.5.1 or later, so add `npm install -g npm@latest`
before the publish step, then remove `NODE_AUTH_TOKEN` and the `NPM_TOKEN`
secret.

### Cutting a release

```bash
git checkout main && git pull
# bump versions (see "Bumping versions"), merge that PR, pull again, then:
git tag -a python/v1.0.0     -m "Python client v1.0.0"     && git push origin python/v1.0.0
git tag -a typescript/v1.0.0 -m "TypeScript client v1.0.0" && git push origin typescript/v1.0.0
git tag -a go/v1.0.0         -m "Go client v1.0.0"         && git push origin go/v1.0.0
```

Watch the run under Actions → Release, approve the environment gate if you set
one, then run the "Verify after publishing" commands above. The manual steps
earlier in this guide still work if you prefer them or need a fallback.
