# Publishing the SecID client SDKs

How to publish the SecID client libraries to their package registries. Three
languages, three distribution channels:

| Language   | Registry | Package name                       | Notes                          |
|------------|----------|------------------------------------|--------------------------------|
| TypeScript | npm      | `@cloudsecurityalliance/secid`     | Scoped, published **public**   |
| Python     | PyPI     | `csa-secid`                        | Flat namespace → `csa-` prefix |
| Go         | (none)   | `github.com/CloudSecurityAlliance/SecID-Client-SDK/go` | Consumed by module path; no publish step |

Naming follows the CSA package-naming convention: registries with a namespace
(npm scopes, Go module paths) keep a simple name under the org namespace; flat
registries (PyPI) carry the `csa-` prefix on the distribution
name. The import module (`secid_client`) and the CLI command (`secid`) stay
simple regardless of the distribution name.

> **Versions are immutable.** Once a version is published to npm or PyPI it
> cannot be overwritten or re-uploaded — a fix requires a new version number.
> Run the dry-run / check step every time before publishing.
>
> **Stay on 0.Y.Z.** A release of 1.0.0 or higher needs Kurt's recorded
> approval first; see [Version policy](#version-policy). The manual steps below
> skip the workflow's checks, so run them yourself: `python3 -I
> scripts/check_release_version.py --tag <tag>` before building, then add
> `--dist python/dist` (Python) or `--npm-pack <dir with the one .tgz>` (npm)
> to check what you are about to upload, and upload exactly those files.

---

## Prerequisites

- **npm:** an account that is a member of the `@cloudsecurityalliance` org/scope
  on npmjs.com, logged in locally (`npm login`). If your account enforces 2FA
  for publishing, npm will prompt for a one-time code during `npm publish`.
- **PyPI:** an account with upload rights, plus an API token. The modern flow
  uses a token (username `__token__`, password `pypi-…`); store it in
  `~/.pypirc` or pass it to `twine`. `twine` itself can be run without a global
  install via `uvx twine`.

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

## Python → PyPI (`csa-secid`)

From `python/`:

```bash
cd python
rm -rf dist/ build/ *.egg-info        # clear any stale artifacts (IMPORTANT — see below)
python3 -m build                       # builds sdist + wheel into dist/
uvx twine check dist/*                 # validate metadata + README rendering (expect PASSED)
uvx twine upload dist/*                # real upload
```

Notes:
- **Always clear `dist/` first.** A stale wheel from an earlier build (e.g. an
  old `secid-0.1.0`) left in `dist/` would get picked up by `twine upload dist/*`
  and either fail or upload the wrong artifact. Alternatively, upload the exact
  files: `twine upload dist/csa_secid-0.1.0*`.
- The **wheel** ships only `secid_client.py` (no tests); the **sdist** is the
  full source archive (includes the test file, which is normal — `pip install`
  uses the wheel).
- The import module stays `secid_client` and the console script stays `secid`
  even though the distribution is `csa-secid`.
- To test the upload against TestPyPI first:
  `uvx twine upload --repository testpypi dist/*`.

Verify after publishing:

```bash
pip index versions csa-secid    # or: curl https://pypi.org/pypi/csa-secid/json
```

A clean end-to-end install check in a throwaway venv:

```bash
python3 -m venv /tmp/secid-check && /tmp/secid-check/bin/pip install csa-secid
/tmp/secid-check/bin/secid "secid:advisory/mitre.org/cve#CVE-2021-44228"
rm -rf /tmp/secid-check
```

## Go

No registry upload. Consumers fetch the module straight from GitHub through the
Go module proxy:

```bash
go get github.com/CloudSecurityAlliance/SecID-Client-SDK/go@v0.1.0
go install github.com/CloudSecurityAlliance/SecID-Client-SDK/go/cmd/secid@v0.1.0
```

**The module is in the `go/` subdirectory, so its tags must be prefixed with
`go/`.** Go maps a module at `<repo>/go` to tags named `go/vX.Y.Z`. A plain
`vX.Y.Z` tag on the repository root is ignored for this module — `go get
…/go@v0.1.0` would fail to find it.

```bash
git checkout main && git pull
cd go && go test ./... && cd ..
# The tag IS the release, so check first. && stops at the first failure.
python3 -I scripts/check_release_version.py --tag go/v0.1.0 &&
  git tag -a go/v0.1.0 -m "Go client v0.1.0" &&
  git push origin go/v0.1.0
```

Verify the proxy has picked it up (may take a minute):

```bash
GOPROXY=https://proxy.golang.org go list -m github.com/CloudSecurityAlliance/SecID-Client-SDK/go@v0.1.0
```

Without any tag, `go get …/go@main` still works, but consumers get a
pseudo-version (`v0.0.0-2026…-abcdef`) rather than `v0.1.0`.

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

**Current registry status** (updated 2026-11-02):

- PyPI `csa-secid`: Trusted Publisher configured (`CloudSecurityAlliance/SecID-Client-SDK`, `release.yml`, environment `pypi`) and `PYPI_PUBLISH_ENABLED=true`. Published at `0.1.0` (`0.Y.Z` pre-1.0 series). On 2026-11-02 `1.0.0` was published outside the intended 0.Y.Z series and then deleted ([incident record](docs/incidents/2026-11-02-pypi-csa-secid-1.0.0.md)). PyPI never lets a file name be reused, even after the file is deleted ([PyPI docs](https://docs.pypi.org/publishing/troubleshooting/)), so the original `csa_secid-1.0.0` wheel and sdist names can never be uploaded again. This project treats `1.0.0` as retired and requires a new version: a future 1.x release starts at `1.0.1` or `1.1.0`, and needs an approval (see [Version policy](#version-policy)).
- npm `@cloudsecurityalliance/secid`: not yet published (`0.1.0` in `package.json`).
- Go: `github.com/CloudSecurityAlliance/SecID-Client-SDK/go@v0.1.0` (`go/v0.1.0` tag). Because `proxy.golang.org` cached an initial `v1.0.0` tag before the switch to `0.Y.Z`, `go/go.mod` includes `retract [v1.0.0, v1.0.1]` (published to the proxy via `go/v1.0.1`) so `@latest` resolves to `v0.1.0` and subsequent `0.Y.Z` releases; future 1.x releases will start at `v1.0.2` or `v1.1.0`.

Local checks: `python -m build` plus `twine check
--strict` PASSED; the wheel holds only `secid_client.py` and installs a working
`secid` CLI in a clean venv. `npm pack --dry-run` lists 7 files; a packed
tarball installs into a scratch project, where both `npx secid` and `import`
work. A scratch Go module imports `…/go` through a `replace` directive and
builds.

---

## Version policy

All three clients stay on the `0.Y.Z` series until Kurt approves a 1.x release.
`scripts/check_release_version.py` enforces this. It was added after
`csa-secid` 1.0.0 was published outside the intended series
([incident record](docs/incidents/2026-11-02-pypi-csa-secid-1.0.0.md)).

| Where | Mode | What happens on failure |
|---|---|---|
| `release.yml`, first step after checkout in `python-build` and `npm-publish` | `--tag "$GITHUB_REF_NAME"` | Nothing is built or published |
| `release.yml`, `python-build` after building, before upload | `--tag … --dist python/dist` (wheel `METADATA`, sdist `PKG-INFO`) | Nothing is uploaded or published |
| `release.yml`, `npm-publish` after `npm pack`, before publishing that same tarball | `--tag … --npm-pack DIR` (`package/package.json` in the `.tgz`) | Nothing is published |
| `release.yml`, `go-tag-check` on `go/v*` tags | `--tag` | The run fails loudly. The Go release has already happened, so retract it (see the job summary) |
| `test.yml`, `package-smoke` (under `ci-passed`) | `--files` | The pull request cannot merge |
| `test.yml`, `python` job (Python 3.11–3.13; the script needs `tomllib`) | unit tests (`scripts/test_check_release_version.py`) | The pull request cannot merge |

It fails when a version is not valid SemVer, when the version files disagree
with each other or with the tag, or when the major version is 1 or higher
(pre-releases such as `1.0.0-rc.1` included) without an approval. With
`dynamic = ["version"]`, `pyproject.toml` must read the version from
`secid_client.py` with Hatchling's default pattern
(`[tool.hatch.version]` is exactly `path = "secid_client.py"`), and the check
reads it the way Hatchling does. The artifact checks then confirm the built
packages carry exactly the tag's version, so Python releases use plain
`X.Y.Z` (PEP 440 rewrites SemVer pre-release suffixes). Run it
before pushing any tag, and above all before a `go/` tag:

```bash
python3 -I scripts/check_release_version.py --tag go/v0.2.0
python3 -I scripts/check_release_version.py --files
python3 -I scripts/test_check_release_version.py
```

### Approving a 1.x release

1. Kurt decides, and the decision is recorded in his words, for example as his
   answer on a `needs-kurt` issue in the program's governance repository.
2. A pull request adds an entry for each exact tag to `RELEASE-APPROVALS.json`:

   ```json
   {
     "tag": "python/v1.0.1",
     "approved_by": "Kurt Seifried",
     "date": "YYYY-MM-DD",
     "reference": "https://github.com/<org>/<repo>/issues/<n>",
     "reason": "Why this release leaves the 0.Y.Z series"
   }
   ```

3. A cross-vendor review opens `reference` and confirms that it records Kurt's
   decision for that exact tag. **The script checks the file's syntax only.** It
   cannot tell a real approval from a made-up one, so this review is what makes
   an approval authentic (`REVIEW.md`, section 1).
4. Bump the version files. Files mode passes once some tag with that version is
   approved. Tag mode passes only for the exact tags listed.

Remember the retired numbers. This project treats PyPI `1.0.0` as retired,
because PyPI never accepts its original file names again. Go `v1.0.0` and
`v1.0.1` are retracted, and the Go module proxy keeps them for good.

---

## Automated publishing

`.github/workflows/release.yml` publishes from GitHub Actions when you push a
release tag by hand:

| Tag | Publishes | Auth |
|---|---|---|
| `python/vX.Y.Z` | PyPI `csa-secid` | **Trusted publishing** (OIDC). No token is stored anywhere. |
| `typescript/vX.Y.Z` | npm `@cloudsecurityalliance/secid` | `NPM_TOKEN` secret, published with `--provenance` |
| `go/vX.Y.Z` | nothing (the tag is the Go release); `go-tag-check` flags a tag that breaks the version policy, after the fact | — |

Both publish jobs first run the version policy check (see [Version policy](#version-policy)),
then check that the tagged commit is an ancestor of `origin/main` and
that the tag matches the version in code, then run the tests, then publish.
**The workflow does nothing until you opt in:** each publish job is skipped
unless a repository variable is set to `true`, so a tag pushed before setup is
harmless.

### One-time setup: PyPI (trusted publishing)

1. Sign in at <https://pypi.org> with the account that should own the project.
2. Go to <https://pypi.org/manage/account/publishing/> and, under "Add a new
   pending publisher" (this reserves the name on first use), enter:
   - PyPI project name: `csa-secid`
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
# Bump versions (see "Bumping versions"), merge that PR and pull again. Then
# list every tag once. The subshell checks each exact tag first, then checks,
# creates and pushes them one at a time. `set -eu` stops at the first failure,
# so a refused tag is never created or pushed, and nothing after it runs.
# An approval covers one exact tag: approving python/v1.0.1 does not let
# go/v1.0.1 through. Works in bash and zsh.
(
  set -eu
  set -- python/v0.1.0 typescript/v0.1.0 go/v0.1.0
  for tag in "$@"; do
    python3 -I scripts/check_release_version.py --tag "$tag"
  done
  for tag in "$@"; do
    python3 -I scripts/check_release_version.py --tag "$tag"
    git tag -a "$tag" -m "Release $tag"
    git push origin "$tag"
  done
)
```

Watch the run under Actions → Release, approve the environment gate if you set
one, then run the "Verify after publishing" commands above. The manual steps
earlier in this guide still work if you prefer them or need a fallback.

## Releasing 1.0 or later: the tag ruleset

Repository ruleset 27284821 blocks creating `go/v1*`, `python/v1*` and `typescript/v1*` tags, with no bypass. Kurt approved it on 2026-11-14; see `docs/incidents/2026-11-02-pypi-csa-secid-1.0.0.md`.

To release a 1.x version, all of these, in order:
1. Kurt's decision is recorded.
2. The exact tag is in `RELEASE-APPROVALS.json` and has passed review.
3. Kurt, or the agent with his explicit go-ahead for that tag, temporarily narrows the ruleset for that one tag. The change is recorded on the release issue, and the ruleset is restored right after the push.

Before the first 2.x release, add `*/v2*` patterns.

