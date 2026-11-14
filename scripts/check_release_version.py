#!/usr/bin/env python3
"""Release version policy check for the SecID client SDKs.

Why this exists: on 2026-11-02 a `python/v1.0.0` tag published `csa-secid`
1.0.0 to PyPI although the program's series was 0.Y.Z. Nothing stopped it, and
PyPI never lets a version number be reused. See
docs/incidents/2026-11-02-pypi-csa-secid-1.0.0.md.

Two modes. Run both with `python3 -I` (isolated mode); stdlib only, Python 3.9+.

  Tag mode, run first in every release.yml job that builds or publishes:

      python3 -I scripts/check_release_version.py --tag python/v0.2.0

  Files mode, run by CI (test.yml) on every pull request and push to main:

      python3 -I scripts/check_release_version.py --files

Both modes fail (exit 1) when:

  * a version is not valid SemVer 2.0.0;
  * the version files disagree with each other (lockstep), or, in tag mode,
    with the tag;
  * the major version is 1 or higher (1.0.0, 1.0.0-rc.1, 2.3.4, ...) and
    RELEASE-APPROVALS.json does not approve it. Tag mode needs an entry for
    that exact tag. Files mode needs an entry for some tag with that version;
  * RELEASE-APPROVALS.json exists and is malformed.

The version files are python/secid_client.py (__version__), python/pyproject.toml
(a static [project] version if present, otherwise it must declare the version
dynamic), typescript/package.json, typescript/src/secid-client.ts (VERSION) and
go/secid.go (Version).

RELEASE-APPROVALS.json is checked for SYNTAX ONLY. This script cannot tell
whether Kurt really approved anything: anyone who can edit the file can add an
entry. An approval is authentic only because every change to that file needs a
cross-vendor review that opens the entry's `reference` and confirms it records
Kurt's decision for that exact tag (REVIEW.md, section 1).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.parse
from typing import Dict, List, Optional, Tuple

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


def _pyproject_version(text: str) -> Optional[str]:
    """Return the static [project] version, or None if the version is dynamic.

    Reads only the [project] table, line by line (tomllib is not in 3.9/3.10).
    """
    table = None
    static = []
    dynamic = False
    for line in text.splitlines():
        stripped = line.strip()
        # [table] or [[array-of-tables]]; either one ends the [project] table.
        header = re.fullmatch(r"\[{1,2}\s*([^\[\]]+?)\s*\]{1,2}\s*(?:#.*)?", stripped)
        if header:
            table = header.group(1).strip()
            continue
        if table != "project":
            continue
        version = re.fullmatch(r'version\s*=\s*"([^"]*)"\s*(?:#.*)?', stripped)
        if version:
            static.append(version.group(1))
        if re.fullmatch(r'dynamic\s*=\s*\[[^\]]*"version"[^\]]*\]\s*(?:#.*)?', stripped):
            dynamic = True
    if len(static) > 1:
        raise CheckError("python/pyproject.toml [project] declares version more than once")
    if static and dynamic:
        raise CheckError("python/pyproject.toml [project] declares version both static and dynamic")
    if static:
        return static[0]
    if not dynamic:
        raise CheckError(
            'python/pyproject.toml [project] has neither version = "..." nor dynamic = ["version"]'
        )
    return None


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
    static = _pyproject_version(_read(repo, "python/pyproject.toml"))
    if static is not None:
        versions["python/pyproject.toml version"] = static
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


def _report_error(message: str) -> None:
    prefix = "::error::" if os.environ.get("GITHUB_ACTIONS") == "true" else "error: "
    print(f"{prefix}{message}", file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tag", help="release tag to check, e.g. python/v0.2.0")
    mode.add_argument("--files", action="store_true", help="check the version files only")
    parser.add_argument(
        "--repo", type=pathlib.Path, default=REPO_ROOT,
        help="repository root (default: the checkout this script lives in)",
    )
    args = parser.parse_args(argv)
    try:
        message = check_tag(args.tag, args.repo) if args.tag is not None else check_files(args.repo)
    except CheckError as exc:
        _report_error(str(exc))
        return 1
    print(f"OK: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
