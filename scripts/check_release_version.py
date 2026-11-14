#!/usr/bin/env python3
"""Release version policy check for the SecID client SDKs.

Why this exists: on 2026-11-02 a `python/v1.0.0` tag published `csa-secid`
1.0.0 to PyPI although the program's series was 0.Y.Z. Nothing stopped it, and
PyPI never accepts the same file name twice. See
docs/incidents/2026-11-02-pypi-csa-secid-1.0.0.md.

Run it with `python3 -I` (isolated mode). Stdlib only; Python 3.11+ (tomllib).

  Tag mode, the first step in every release.yml job that builds or publishes:

      python3 -I scripts/check_release_version.py --tag python/v0.2.0

  Artifact mode, in release.yml after building and before uploading or
  publishing. It checks the built packages themselves:

      python3 -I scripts/check_release_version.py --tag python/v0.2.0 --dist python/dist
      python3 -I scripts/check_release_version.py --tag typescript/v0.2.0 --npm-pack DIR

  Files mode, run by CI (test.yml) on every pull request and push to main:

      python3 -I scripts/check_release_version.py --files

Tag and files mode fail (exit 1) when:

  * a version is not valid SemVer 2.0.0;
  * the version files disagree with each other (lockstep), or, in tag mode,
    with the tag;
  * the major version is 1 or higher (1.0.0, 1.0.0-rc.1, 2.3.4, ...) and
    RELEASE-APPROVALS.json does not approve it. Tag mode needs an entry for
    that exact tag. Files mode needs an entry for some tag with that version;
  * RELEASE-APPROVALS.json exists and is malformed.

Artifact mode runs the tag check, then also fails unless the built packages
carry exactly the tag's version and the right name. That means the wheel's
METADATA and the sdist's PKG-INFO for --dist, and package/package.json inside
the single .tgz for --npm-pack.

The version files are python/secid_client.py (__version__),
python/pyproject.toml, typescript/package.json, typescript/src/secid-client.ts
(VERSION) and go/secid.go (Version). pyproject.toml either has a static
[project] version, or declares it dynamic with Hatchling reading
python/secid_client.py by its default pattern ([tool.hatch.version] is exactly
path = "secid_client.py"). In the dynamic case the check reads the version the
way Hatchling would, so a version source that diverges from __version__ fails.

RELEASE-APPROVALS.json is checked for SYNTAX ONLY. This script cannot tell
whether Kurt really approved anything: anyone who can edit the file can add an
entry. An approval is authentic only because every change to that file needs a
cross-vendor review that opens the entry's `reference` and confirms it records
Kurt's decision for that exact tag (REVIEW.md, section 1).
"""

from __future__ import annotations

import argparse
import datetime
import email.parser
import json
import os
import pathlib
import re
import sys
import tarfile
import urllib.parse
import zipfile
from typing import Dict, List, Optional, Tuple

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11; main() refuses to run
    tomllib = None  # type: ignore[assignment]

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
APPROVALS_FILE = "RELEASE-APPROVALS.json"
APPROVER = "Kurt Seifried"
APPROVAL_KEYS = ("tag", "approved_by", "date", "reference", "reason")
APPROVALS_TOP_LEVEL_KEYS = {"about", "approvals"}

TAG_PREFIXES = ("python", "typescript", "go")
TAG_RE = re.compile(r"(python|typescript|go)/v(.*)", re.ASCII | re.DOTALL)

# SemVer 2.0.0 (https://semver.org), with [0-9] instead of \d so that
# non-ASCII digits never match, applied with fullmatch so that a trailing
# newline never matches either.
_NUM = r"(?:0|[1-9][0-9]*)"
_PRE_ID = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_BUILD_ID = r"[0-9A-Za-z-]+"
SEMVER_RE = re.compile(
    rf"(?P<major>{_NUM})\.(?P<minor>{_NUM})\.(?P<patch>{_NUM})"
    rf"(?:-{_PRE_ID}(?:\.{_PRE_ID})*)?"
    rf"(?:\+{_BUILD_ID}(?:\.{_BUILD_ID})*)?",
    re.ASCII,
)
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)

# Hatchling's default version pattern (hatchling/version/core.py), applied the
# way Hatchling applies it: re.search with MULTILINE, first match wins.
HATCH_DEFAULT_PATTERN = r"""(?i)^(__version__|VERSION) *= *([\'"])v?(?P<version>.+?)\2"""
HATCH_VERSION_CONFIG = {"path": "secid_client.py"}
PYPROJECT = "python/pyproject.toml"


class CheckError(Exception):
    """A policy or consistency failure. The message says what to fix."""


def parse_semver(version: str) -> int:
    """Return the major version, or raise CheckError if `version` is not SemVer."""
    match = SEMVER_RE.fullmatch(version)
    if match is None:
        raise CheckError(f"{version!r} is not a valid SemVer 2.0.0 version (MAJOR.MINOR.PATCH)")
    return int(match.group("major"))


def parse_tag(tag: str) -> Tuple[str, str]:
    """Split a release tag into (language, version). The version is not validated."""
    match = TAG_RE.fullmatch(tag)
    if match is None:
        raise CheckError(
            f"{tag!r} is not a release tag; expected one of "
            + ", ".join(f"{p}/vX.Y.Z" for p in TAG_PREFIXES)
        )
    return match.group(1), match.group(2)


def _read(repo: pathlib.Path, rel: str) -> str:
    path = repo / rel
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise CheckError(f"version file {rel} is missing") from None


def _single(pattern: str, text: str, label: str) -> str:
    found = re.findall(pattern, text, re.MULTILINE)
    if len(found) != 1:
        raise CheckError(f"expected exactly one version in {label}, found {len(found)}")
    return found[0]


def _table(data: dict, *keys: str) -> dict:
    """Return data[k1][k2]..., or {} if absent; raise if a level is not a table."""
    for key in keys:
        data = data.get(key, {})
        if not isinstance(data, dict):
            raise CheckError(f"{PYPROJECT}: {'.'.join(keys)} must be a table")
    return data


def _load_pyproject(repo: pathlib.Path) -> dict:
    try:
        return tomllib.loads(_read(repo, PYPROJECT))
    except tomllib.TOMLDecodeError as exc:
        raise CheckError(f"{PYPROJECT} is not valid TOML: {exc}") from None


def _pyproject_versions(repo: pathlib.Path) -> Dict[str, str]:
    """Return the version pyproject.toml gives the built package, labelled.

    Static: [project] version. Dynamic: only Hatchling's default regex source
    reading python/secid_client.py is accepted, and the version is read the
    way Hatchling reads it, so it joins the lockstep comparison.
    """
    data = _load_pyproject(repo)
    project = _table(data, "project")
    dynamic = project.get("dynamic", [])
    if not isinstance(dynamic, list):
        raise CheckError(f"{PYPROJECT}: [project] dynamic must be a list")
    static = project.get("version")
    if static is not None and "version" in dynamic:
        raise CheckError(f"{PYPROJECT} [project] declares version both static and dynamic")
    if static is not None:
        if not isinstance(static, str):
            raise CheckError(f"{PYPROJECT} [project] version must be a string")
        return {f"{PYPROJECT} [project] version": static}
    if "version" not in dynamic:
        raise CheckError(f'{PYPROJECT} [project] has neither version = "..." nor dynamic = ["version"]')

    backend = _table(data, "build-system").get("build-backend")
    if backend != "hatchling.build":
        raise CheckError(
            f"{PYPROJECT}: a dynamic version is only checked for build-backend "
            f'"hatchling.build", found {backend!r}'
        )
    if "hooks" in _table(data, "tool", "hatch", "metadata"):
        raise CheckError(f"{PYPROJECT}: [tool.hatch.metadata.hooks] can rewrite the version; not allowed")
    config = _table(data, "tool", "hatch").get("version")
    if config != HATCH_VERSION_CONFIG:
        raise CheckError(
            f'{PYPROJECT}: [tool.hatch.version] must be exactly path = "secid_client.py" '
            f"(the default regex source on a checked version file), found {config!r}"
        )
    source = "python/" + HATCH_VERSION_CONFIG["path"]
    match = re.search(HATCH_DEFAULT_PATTERN, _read(repo, source), re.MULTILINE)
    if match is None:
        raise CheckError(f"Hatchling's default pattern finds no version in {source}")
    return {f"{PYPROJECT} dynamic version (as Hatchling reads {source})": match.group("version")}


def read_versions(repo: pathlib.Path) -> Dict[str, str]:
    """Return {label: version} for every version file in the repository."""
    versions = {
        "python/secid_client.py __version__": _single(
            r'^__version__\s*=\s*"([^"]*)"', _read(repo, "python/secid_client.py"),
            "python/secid_client.py (__version__)",
        ),
        "typescript/src/secid-client.ts VERSION": _single(
            r'^export const VERSION\s*=\s*"([^"]*)"', _read(repo, "typescript/src/secid-client.ts"),
            "typescript/src/secid-client.ts (VERSION)",
        ),
        "go/secid.go Version": _single(
            r'^\s*(?:const\s+)?Version\s*=\s*"([^"]*)"', _read(repo, "go/secid.go"),
            "go/secid.go (Version)",
        ),
    }
    try:
        package = json.loads(_read(repo, "typescript/package.json"))
    except json.JSONDecodeError as exc:
        raise CheckError(f"typescript/package.json is not valid JSON: {exc}") from None
    if not isinstance(package, dict) or not isinstance(package.get("version"), str):
        raise CheckError('typescript/package.json has no string "version"')
    versions["typescript/package.json version"] = package["version"]
    versions.update(_pyproject_versions(repo))
    return versions


def lockstep_version(versions: Dict[str, str]) -> str:
    """Return the one version all files agree on, or raise CheckError."""
    for label, version in versions.items():
        try:
            parse_semver(version)
        except CheckError as exc:
            raise CheckError(f"{label}: {exc}") from None
    distinct = sorted(set(versions.values()))
    if len(distinct) != 1:
        detail = "; ".join(f"{label} = {v}" for label, v in sorted(versions.items()))
        raise CheckError(f"version files are out of lockstep: {detail}")
    return distinct[0]


def _reject_duplicate_keys(pairs: List[Tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckError(f"{APPROVALS_FILE}: duplicate key {key!r}")
        result[key] = value
    return result


def _check_reference(ref: object, where: str) -> None:
    if not isinstance(ref, str) or not ref:
        raise CheckError(f"{where}: reference must be a non-empty string")
    if any(ch.isspace() or ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F for ch in ref):
        raise CheckError(f"{where}: reference contains whitespace or control characters")
    parsed = urllib.parse.urlsplit(ref)
    if parsed.scheme != "https" or not parsed.hostname:
        raise CheckError(f"{where}: reference must be an https:// URL to the recorded decision")


def load_approvals(repo: pathlib.Path) -> Dict[str, dict]:
    """Return {tag: entry} from RELEASE-APPROVALS.json, validating its syntax.

    A missing file means no approvals. A malformed file is an error, whether or
    not the release being checked needs it.
    """
    path = repo / APPROVALS_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise CheckError(f"{APPROVALS_FILE} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise CheckError(f"{APPROVALS_FILE} must be a JSON object")
    unknown = set(data) - APPROVALS_TOP_LEVEL_KEYS
    if unknown:
        raise CheckError(f"{APPROVALS_FILE}: unknown top-level keys {sorted(unknown)}")
    if "about" in data and not isinstance(data["about"], str):
        raise CheckError(f"{APPROVALS_FILE}: about must be a string")
    entries = data.get("approvals")
    if not isinstance(entries, list):
        raise CheckError(f'{APPROVALS_FILE}: "approvals" must be a list')

    approvals: Dict[str, dict] = {}
    for index, entry in enumerate(entries):
        where = f"{APPROVALS_FILE} approvals[{index}]"
        if not isinstance(entry, dict):
            raise CheckError(f"{where} must be an object")
        keys = set(entry)
        if keys != set(APPROVAL_KEYS):
            missing = sorted(set(APPROVAL_KEYS) - keys)
            extra = sorted(keys - set(APPROVAL_KEYS))
            raise CheckError(f"{where}: missing keys {missing}, unexpected keys {extra}")
        for key in APPROVAL_KEYS:
            if not isinstance(entry[key], str):
                raise CheckError(f"{where}: {key} must be a string")
        tag = entry["tag"]
        try:
            parse_semver(parse_tag(tag)[1])
        except CheckError as exc:
            raise CheckError(f"{where}: {exc}") from None
        if entry["approved_by"] != APPROVER:
            raise CheckError(f"{where}: approved_by must be {APPROVER!r}")
        if DATE_RE.fullmatch(entry["date"]) is None:
            raise CheckError(f"{where}: date must be YYYY-MM-DD")
        try:
            datetime.date.fromisoformat(entry["date"])
        except ValueError:
            raise CheckError(f"{where}: date {entry['date']!r} is not a calendar date") from None
        _check_reference(entry["reference"], where)
        if not entry["reason"].strip():
            raise CheckError(f"{where}: reason must not be empty")
        if tag in approvals:
            raise CheckError(f"{where}: tag {tag!r} is listed more than once")
        approvals[tag] = entry
    return approvals


def check_tag(tag: str, repo: pathlib.Path) -> str:
    """Check a release tag against the repository. Return a success message."""
    _language, version = parse_tag(tag)
    major = parse_semver(version)
    files_version = lockstep_version(read_versions(repo))
    if version != files_version:
        raise CheckError(f"tag {tag} says {version} but the version files say {files_version}")
    approvals = load_approvals(repo)
    if major >= 1:
        if tag not in approvals:
            raise CheckError(
                f"{tag} is outside the 0.Y.Z series and {APPROVALS_FILE} does not approve "
                f"this exact tag. A 1.x release needs Kurt's recorded decision first: see "
                f"PUBLISHING.md, 'Version policy'."
            )
        entry = approvals[tag]
        return (
            f"{tag}: version {version} matches the version files; approved by "
            f"{entry['approved_by']} on {entry['date']} ({entry['reference']})"
        )
    return f"{tag}: version {version} matches the version files and is in the 0.Y.Z series"


def check_files(repo: pathlib.Path) -> str:
    """Check the version files alone (CI on pull requests). Return a success message."""
    version = lockstep_version(read_versions(repo))
    approvals = load_approvals(repo)
    if parse_semver(version) >= 1:
        approved = sorted(t for t in approvals if parse_tag(t)[1] == version)
        if not approved:
            raise CheckError(
                f"the version files say {version}, outside the 0.Y.Z series, and "
                f"{APPROVALS_FILE} approves no tag with that version. A 1.x version needs "
                f"Kurt's recorded decision first: see PUBLISHING.md, 'Version policy'."
            )
        return f"version files agree on {version}; approved tags: {', '.join(approved)}"
    return f"version files agree on {version} (0.Y.Z series)"


def _normalize_dist_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _metadata_name_version(text: str, where: str) -> Tuple[str, str]:
    """Return (Name, Version) from core metadata (wheel METADATA, sdist PKG-INFO)."""
    headers = email.parser.HeaderParser().parsestr(text)
    names = headers.get_all("Name") or []
    versions = headers.get_all("Version") or []
    if len(names) != 1 or len(versions) != 1:
        raise CheckError(f"{where}: expected one Name and one Version header")
    return names[0].strip(), versions[0].strip()


def _only_files(directory: pathlib.Path, label: str) -> List[pathlib.Path]:
    if not directory.is_dir():
        raise CheckError(f"{label} {directory} is not a directory")
    return sorted(directory.iterdir())


def _version_mismatch(where: str, found: str, tag: str, version: str) -> CheckError:
    hint = ""
    if any(ch in version for ch in "-+"):
        hint = " (PEP 440 rewrites SemVer pre-release and build suffixes, so release Python with plain X.Y.Z)"
    return CheckError(f"{where} says version {found!r} but the tag {tag} says {version!r}{hint}")


def check_python_dist(tag: str, dist_dir: pathlib.Path, repo: pathlib.Path) -> str:
    """Check that the built wheel and sdist carry exactly the tag's version."""
    language, version = parse_tag(tag)
    if language != "python":
        raise CheckError(f"--dist checks Python distributions, but {tag} is not a python/ tag")
    project_name = _table(_load_pyproject(repo), "project").get("name")
    if not isinstance(project_name, str):
        raise CheckError(f"{PYPROJECT} [project] has no name")
    files = _only_files(dist_dir, "--dist")
    wheels = [f for f in files if f.name.endswith(".whl")]
    sdists = [f for f in files if f.name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1 or len(files) != 2:
        raise CheckError(
            f"{dist_dir} must hold exactly one wheel and one sdist, found "
            f"{[f.name for f in files]}"
        )

    found = []
    with zipfile.ZipFile(wheels[0]) as wheel:
        members = [n for n in wheel.namelist() if re.fullmatch(r"[^/]+\.dist-info/METADATA", n)]
        if len(members) != 1:
            raise CheckError(f"{wheels[0].name}: expected one *.dist-info/METADATA, found {members}")
        found.append((f"{wheels[0].name} METADATA", wheel.read(members[0]).decode("utf-8")))
    with tarfile.open(sdists[0], "r:gz") as sdist:
        members = [m for m in sdist.getmembers() if m.isfile() and re.fullmatch(r"[^/]+/PKG-INFO", m.name)]
        if len(members) != 1:
            raise CheckError(f"{sdists[0].name}: expected one top-level PKG-INFO, found {len(members)}")
        handle = sdist.extractfile(members[0])
        found.append((f"{sdists[0].name} PKG-INFO", handle.read().decode("utf-8")))

    for where, text in found:
        name, built = _metadata_name_version(text, where)
        if _normalize_dist_name(name) != _normalize_dist_name(project_name):
            raise CheckError(f"{where} names the package {name!r}, expected {project_name!r}")
        if built != version:
            raise _version_mismatch(where, built, tag, version)
    return f"{wheels[0].name} and {sdists[0].name} carry {project_name} {version}"


def check_npm_pack(tag: str, pack_dir: pathlib.Path, repo: pathlib.Path) -> str:
    """Check that the single packed npm tarball carries exactly the tag's version."""
    language, version = parse_tag(tag)
    if language != "typescript":
        raise CheckError(f"--npm-pack checks an npm tarball, but {tag} is not a typescript/ tag")
    try:
        expected_name = json.loads(_read(repo, "typescript/package.json")).get("name")
    except (json.JSONDecodeError, AttributeError):
        raise CheckError("typescript/package.json has no name") from None
    files = _only_files(pack_dir, "--npm-pack")
    if len(files) != 1 or not files[0].name.endswith(".tgz"):
        raise CheckError(f"{pack_dir} must hold exactly one .tgz, found {[f.name for f in files]}")
    tarball = files[0]
    with tarfile.open(tarball, "r:gz") as archive:
        members = [m for m in archive.getmembers() if m.isfile() and m.name == "package/package.json"]
        if len(members) != 1:
            raise CheckError(f"{tarball.name}: expected one package/package.json, found {len(members)}")
        try:
            packed = json.loads(archive.extractfile(members[0]).read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise CheckError(f"{tarball.name}: package/package.json is not valid JSON") from None
    if not isinstance(packed, dict):
        raise CheckError(f"{tarball.name}: package/package.json is not an object")
    if packed.get("name") != expected_name:
        raise CheckError(f"{tarball.name} names the package {packed.get('name')!r}, expected {expected_name!r}")
    if packed.get("version") != version:
        raise _version_mismatch(f"{tarball.name} package/package.json", packed.get("version"), tag, version)
    return f"{tarball.name} carries {expected_name} {version}"


def _report_error(message: str) -> None:
    prefix = "::error::" if os.environ.get("GITHUB_ACTIONS") == "true" else "error: "
    print(f"{prefix}{message}", file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tag", help="release tag to check, e.g. python/v0.2.0")
    mode.add_argument("--files", action="store_true", help="check the version files only")
    artifact = parser.add_mutually_exclusive_group()
    artifact.add_argument(
        "--dist", type=pathlib.Path, metavar="DIR",
        help="with --tag python/v...: also check the built wheel and sdist in DIR",
    )
    artifact.add_argument(
        "--npm-pack", type=pathlib.Path, metavar="DIR",
        help="with --tag typescript/v...: also check the one .tgz in DIR",
    )
    parser.add_argument(
        "--repo", type=pathlib.Path, default=REPO_ROOT,
        help="repository root (default: the checkout this script lives in)",
    )
    args = parser.parse_args(argv)
    if (args.dist or args.npm_pack) and args.tag is None:
        parser.error("--dist and --npm-pack need --tag")
    if tomllib is None:
        _report_error(f"this check needs Python 3.11 or newer (tomllib); this is {sys.version.split()[0]}")
        return 1
    try:
        if args.tag is None:
            messages = [check_files(args.repo)]
        else:
            messages = [check_tag(args.tag, args.repo)]
            if args.dist:
                messages.append(check_python_dist(args.tag, args.dist, args.repo))
            if args.npm_pack:
                messages.append(check_npm_pack(args.tag, args.npm_pack, args.repo))
    except CheckError as exc:
        _report_error(str(exc))
        return 1
    for message in messages:
        print(f"OK: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
