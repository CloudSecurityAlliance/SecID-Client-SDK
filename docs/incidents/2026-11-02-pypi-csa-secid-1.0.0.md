# Incident: `csa-secid` 1.0.0 published to PyPI outside the 0.Y.Z series

- **Date of incident:** 2026-11-02
- **Written:** 2026-11-14 by Claude (SecID governing agent), for [#45](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/issues/45). It had not been recorded until then.
- **Status:** release withdrawn and series corrected the same day ([#37](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/pull/37)). A release check that would have caught it is added with this record.

## Summary

A push of tag `python/v1.0.0` published `csa-secid` 1.0.0 to PyPI. The program's intended series was 0.Y.Z. Kurt deleted the release from PyPI within half an hour, and the SDK moved to 0.1.0 the same day. Nothing in the release path checked which series a version belonged to, so nothing would have stopped it happening again.

## Timeline (UTC)

| Time | Event | Source |
|---|---|---|
| 2026-04-05 | Commit `6dd528f` sets `typescript/package.json` and the static version in `python/pyproject.toml` to `1.0.0`. | `git show 6dd528f` |
| 2026-09-25 03:43 | [#28](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/pull/28) ("Prepare docs and packaging for the first publish") sets `__version__`, the TypeScript `VERSION` and the Go `Version` to `1.0.0`, and adds `release.yml`. From here on every version file says `1.0.0`. | `git show 4f357ff` |
| 2026-11-02 15:24:19 | Repository variable `PYPI_PUBLISH_ENABLED` is last changed. Its value is now `true`, which switches on the PyPI publish job. | `gh variable list` |
| 15:34:22 | [#35](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/pull/35) merges as `1dc8336`. It renames the PyPI distribution to `csa-secid` and makes `release.yml` check that a tagged commit is on `main`. Its issue, [#34](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/issues/34), is titled "…harden release.yml for v1.0.0 publish". | #35, #34 |
| 15:34:30 | A push of tag `python/v1.0.0` (commit `1dc8336`) starts [Release run 41472918524](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/actions/runs/41472918524). The agent then running the program (Gemini) cut the tag. | run |
| 15:35:03 | "Build Python distribution" succeeds. Its tag-matches-`__version__` check passes, because both say `1.0.0`. | run |
| 15:35:24 | "Publish to PyPI" succeeds: `csa_secid-1.0.0` is on PyPI. The run concludes **success**. | run |
| 15:55:01 | Kurt: *"oh we need to delete that 1.0.0 release asap. we need to do like a 0.Y.Z release series first"* | agent prompt history ¹ |
| 16:02:30 | Kurt: *"ok I deleted it, so we'll have to do a 1.0.1 I guess?"* | agent prompt history ¹ |
| 16:05:00 | [#37](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/pull/37) (issue [#36](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/issues/36)) merges as `ffb6a11`. Every version file goes to `0.1.0`, and `go/go.mod` gains `retract [v1.0.0, v1.0.1]`. Tags `python/v0.1.0`, `go/v0.1.0` and `go/v1.0.1` point at this commit. | #37, `git ls-remote --tags` |
| 16:05:08 | [Release run 41477968045](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/actions/runs/41477968045) (tag `python/v0.1.0`) starts. It publishes 0.1.0 through trusted publishing (OIDC) at 16:06:32. | run |
| 17:28:27 | [#39](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/pull/39) adds a CI gate that the version files agree. It does not check which series they are on. | #39 |
| 2026-11-03 04:03:05 | [#42](https://github.com/CloudSecurityAlliance/SecID-Client-SDK/pull/42) adds `REVIEW.md`, which states the 0.Y.Z rule for reviewers. No code enforces it. | #42 |
| 2026-11-13 | An independent review of the program's records finds the incident in no record. | governance review ² |
| 2026-11-14 | PyPI lists only `0.1.0` for `csa-secid`, and tag `python/v1.0.0` is no longer in this repository. The Go module proxy lists v0.1.0, v1.0.0 and v1.0.1, and resolves `@latest` to v0.1.0. | checked 2026-11-14 |

¹ The program agent's prompt history (Antigravity CLI, conversation `2960ce20`), which is local and not published.
² CSA-Internal-Governance/SecID (private), `reviews/2026-11-13/review-3-records-honesty.md` R-04 and `review-5-code-security.md` F19.

## Impact

- **PyPI will never accept the 1.0.0 files again.** PyPI never lets a file name be reused, even after the file is deleted ([PyPI docs](https://docs.pypi.org/publishing/troubleshooting/)). The two files this release uploaded, `csa_secid-1.0.0-py3-none-any.whl` and `csa_secid-1.0.0.tar.gz`, can therefore never be uploaded again. This project treats 1.0.0 as retired and requires a new version, so the first 1.x release must be 1.0.1 or later. That is why Kurt asked about "a 1.0.1".
- **Anyone who installed 1.0.0 is stranded above the 0.Y.Z series.** 1.0.0 was on PyPI from 15:35:24 until Kurt deleted it, no later than 16:02:30. An install from that window sits above every 0.Y.Z release, so `pip install --upgrade csa-secid` keeps it and never offers a 0.Y.Z version. A requirement pinned to `csa-secid==1.0.0` no longer installs from PyPI.
- **We don't know whether anyone installed it.** Downloads during the window are unknown. PyPI's public download logs on BigQuery (`bigquery-public-data.pypi.file_downloads`) have not been queried for this file, and we cannot see mirrors that synced during the window.
- **Go:** v1.0.0, and v1.0.1 (which exists only to carry the retraction), stay in the Go module proxy permanently, marked retracted. The first 1.x Go release must be v1.0.2 or later.
- **The fault was the version number, not the code.** The 1.0.0 wheel was built by the normal release workflow from commit `1dc8336` on `main`.

## Cause

- **Nothing checked which series a version belonged to.** `release.yml` checked only that the tag matched `__version__`. Every version file had said `1.0.0` since #28 in September, so tag and code agreed and the check passed.
- **The 0.Y.Z policy existed only in intent.** Before the release it was not written down in this repository: "0.Y.Z" first appears in #37, merged half an hour after the release. #42 then wrote it into `REVIEW.md`, but only as a rule for reviewers to apply.
- **Nothing between the tag and PyPI needed a person.** The `pypi` environment checks only that the tag matches `python/v*`, with no required reviewer. `PYPI_PUBLISH_ENABLED`, which switches publishing on, was last changed ten minutes before the tag. The program lets its agent cut releases, so a check in code is the only gate between an agent's tag and the registry.
- **The version was visible but nothing compared it with the intent.** Issue #34's title said "…for v1.0.0 publish".

## Fix and follow-up

- **#37** (issue #36, 16:05:00) moved all three clients to `0.1.0` and wrote down the 0.Y.Z series. In `go/go.mod` it added `retract [v1.0.0, v1.0.1]`. Tag `go/v1.0.1` exists only so the proxy reads that retraction at the highest known version, and `go/v0.1.0` is the real Go release.
- **`python/v0.1.0`** (run 41477968045) published `csa-secid` 0.1.0 to PyPI through trusted publishing (OIDC).
- **#35** (issue #34) is the commit that was released, merged eight seconds before the tag. It renamed the distribution to `csa-secid` and added the check that a tagged commit is on `main`.
- **#39 and #42** added the lockstep CI gate and the written review rule.
- **This change** adds the incident record and the release version check below.

## The new check

The check is `scripts/check_release_version.py`, stdlib only (Python 3.11+, for `tomllib`), run with `python3 -I`. Its unit tests are in `scripts/test_check_release_version.py`.

- **Tag mode** (`--tag python/v0.2.0`) is the first step after checkout in `release.yml`'s `python-build` and `npm-publish` jobs, before anything is built or published. `python-publish` needs `python-build`, so a refused tag never reaches PyPI. The check fails when:
  - the version is not valid SemVer 2.0.0;
  - the version files disagree with each other or with the tag. The files are `python/secid_client.py`, `python/pyproject.toml`, `typescript/package.json`, `typescript/src/secid-client.ts` and `go/secid.go`. A dynamic version in `pyproject.toml` must come from Hatchling's default source reading `secid_client.py`, and the check reads it the way Hatchling would;
  - the major version is 1 or higher, pre-releases such as `1.0.0-rc.1` included, unless `RELEASE-APPROVALS.json` lists that exact tag. The entry needs `approved_by` set to "Kurt Seifried", a `date`, a `reference` URL to the recorded decision and a `reason`.
- **Artifact mode** checks what is about to be released, after building and before uploading. `--dist python/dist` reads the wheel's `METADATA` and the sdist's `PKG-INFO`. `--npm-pack DIR` reads `package/package.json` inside the one packed `.tgz`, and `npm-publish` then publishes exactly that tarball. Either fails unless name and version match the tag exactly. This is the backstop for anything that changes the built version without changing the checked files.
- **Files mode** (`--files`) runs in CI's `package-smoke` job, under the required `ci-passed` gate, on every pull request and push to `main`. It replaces the inline lockstep script and adds the SemVer and series rules. A pull request that moves the version files to 1.x without an approval therefore fails before any tag exists.
- **Go:** `release.yml` now also runs on `go/v*` tags. The job `go-tag-check` runs the same check, fails loudly and writes what to do into the job summary. It cannot stop anything, because the tag is the release.
- **Unit tests** run in CI's `python` job on Python 3.11 to 3.13. They use fixture repositories only, never real tags. They show that:
  - `python/v1.0.0` fails when every file says 1.0.0;
  - `python/v0.2.0` passes when the files say 0.2.0;
  - a listed approval passes, but only for its exact tag;
  - malformed approvals, bad SemVer and broken lockstep all fail;
  - a dynamic version source that diverges from the checked files fails;
  - built wheels, sdists and npm tarballs whose version or name differs from the tag fail.

**Replay against the real history.** Run on the files at the released commit `1dc8336`, `--tag python/v1.0.0` exits 1:

```
error: python/v1.0.0 is outside the 0.Y.Z series and RELEASE-APPROVALS.json does not approve this exact tag. ...
```

Run on the files at #28's commit `4f357ff`, `--files` exits 1. Had this CI gate existed, it would have flagged the version from 2026-09-25 on. On the files at `ffb6a11` (#37), `--tag python/v0.1.0` passes.

**Real builds.** A real Hatchling build of this repository (`csa_secid-0.1.0` wheel and sdist) and a real `npm pack` (`cloudsecurityalliance-secid-0.1.0.tgz`) pass artifact mode for the `v0.1.0` tags. Pointing `[tool.hatch.version]` at a file that says 1.0.1 builds `csa_secid-1.0.1`. Tag mode refuses that configuration, and artifact mode on its own refuses the built files.

## Limits of the check

1. **`RELEASE-APPROVALS.json` is checked for syntax only.** The script cannot tell whether Kurt approved anything, and anyone who can edit the file can add an entry. An approval is authentic only because every change to the file needs a cross-vendor review. That review opens the entry's `reference` and confirms it records Kurt's decision, in his own words, for that exact tag (`REVIEW.md`, section 1).
2. **Go is flagged, not stopped.** A `go/v*` tag is public as soon as it is pushed.
3. **A tag on an old commit runs the old workflow.** GitHub runs `release.yml` as it stood at the tagged commit, and before this change it had no version check. The `main` commits from #28 (`4f357ff`) to `1dc8336` carry the old workflow and version files at `1.0.0`. Tagging one of them `typescript/v1.0.0` would publish 1.0.0 to npm once `NPM_PUBLISH_ENABLED` is set. It is not set today.
4. **The agent works with Kurt's credentials.** Whoever holds them can edit the approvals file in a pull request, change the workflow, or push a tag. The check turns an unnoticed mistake into a visible change that needs review. It does not stop a deliberate one.

## Recommendation (Kurt's decision)

**Add a tag ruleset to this repository that restricts creation of tags matching `go/v1*`, `python/v1*` and `typescript/v1*`, with an empty bypass list.** Add a pattern such as `go/v2*` before any later major version.

- **Why:** it is the only control that *prevents* a premature Go release rather than flagging it. Rulesets apply whatever workflow a commit carries, so it also closes limit 3 for all three languages.
- **Why an empty bypass list:** the agent works with Kurt's credentials, so a bypass for Kurt is a bypass for the agent. To release a 1.x version, Kurt edits the ruleset himself for that tag, after recording the approval.
- **Why it is Kurt's:** changing a repository ruleset is a permissions change, which the program's rules reserve for Kurt. This change touches no repository settings.
- **What it does not do:** an admin credential can still edit the ruleset. It relies on the agent not changing settings, which the program's rules already forbid, and it turns a mistake into a deliberate breach of those rules.
- **If Kurt declines:** limits 2 and 3 stay open. `go-tag-check`, the files-mode CI gate and `REVIEW.md` remain the controls.

## The release pause

Under the program's rule, a change withdrawn for substance pauses changes of that kind until three things hold:

1. the cause is written up (this record);
2. the fix is merged (#37);
3. a check exists that would have caught it (the check above).

SDK releases have been paused under that rule. Once this change merges, all three hold, and the governing agent records the lift.
