#!/usr/bin/env python3
"""Unit tests for check_release_version.py. Stdlib unittest; Python 3.9+.

Run from anywhere:

    python3 -I scripts/test_check_release_version.py -v

Every case builds a throwaway fixture repository in a fresh temporary
directory. No real tags are created or read.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

# `python3 -I` keeps this directory off sys.path, so load the module by path.
SCRIPT = pathlib.Path(__file__).resolve().parent / "check_release_version.py"
_spec = importlib.util.spec_from_file_location("check_release_version", SCRIPT)
crv = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = crv
_spec.loader.exec_module(crv)

APPROVAL = {
    "tag": "python/v1.0.1",
    "approved_by": "Kurt Seifried",
    "date": "2026-12-01",
    "reference": "https://github.com/CSA-Internal-Governance/SecID/issues/999",
    "reason": "Fixture: the API is stable and Kurt decided to leave the 0.Y.Z series.",
}


def make_repo(root: pathlib.Path, version: str = "0.1.0", overrides: dict | None = None,
              approvals: object = None, pyproject: str | None = None) -> pathlib.Path:
    """Write the five version files (all at `version` unless overridden)."""
    v = dict(python=version, ts_pkg=version, ts_src=version, go=version)
    v.update(overrides or {})
    (root / "python").mkdir()
    (root / "typescript" / "src").mkdir(parents=True)
    (root / "go").mkdir()
    (root / "python" / "secid_client.py").write_text(
        f'"""client"""\n\n__version__ = "{v["python"]}"\n\nUA = f"secid-python-client/{{__version__}}"\n'
    )
    (root / "python" / "pyproject.toml").write_text(pyproject if pyproject is not None else (
        '[project]\nname = "csa-secid"\ndynamic = ["version"]  # read from __version__\n\n'
        '[tool.hatch.version]\npath = "secid_client.py"\n'
    ))
    (root / "typescript" / "package.json").write_text(
        json.dumps({"name": "@cloudsecurityalliance/secid", "version": v["ts_pkg"]}, indent=2)
    )
    (root / "typescript" / "src" / "secid-client.ts").write_text(
        f'export const VERSION = "{v["ts_src"]}";\nconst ua = `secid-typescript-client/${{VERSION}}`;\n'
    )
    (root / "go" / "secid.go").write_text(
        f'package secid\n\n// Version is the client version.\nconst Version = "{v["go"]}"\n'
    )
    if approvals is not None:
        text = approvals if isinstance(approvals, str) else json.dumps(approvals, indent=2)
        (root / crv.APPROVALS_FILE).write_text(text)
    return root


class RepoCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assertFails(self, fn, *args, contains: str = "") -> None:
        with self.assertRaises(crv.CheckError) as ctx:
            fn(*args)
        self.assertIn(contains, str(ctx.exception))


class IncidentReplay(RepoCase):
    """The 2026-11-02 state: every version file said 1.0.0 and the tag was python/v1.0.0."""

    def test_python_v1_0_0_fails_without_approval(self):
        make_repo(self.root, "1.0.0")
        self.assertFails(crv.check_tag, "python/v1.0.0", self.root, contains="outside the 0.Y.Z series")

    def test_python_v1_0_0_fails_with_empty_approvals_file(self):
        make_repo(self.root, "1.0.0", approvals={"about": "x", "approvals": []})
        self.assertFails(crv.check_tag, "python/v1.0.0", self.root, contains="outside the 0.Y.Z series")

    def test_files_at_1_0_0_fail_in_ci_too(self):
        make_repo(self.root, "1.0.0")
        self.assertFails(crv.check_files, self.root, contains="outside the 0.Y.Z series")

    def test_typescript_and_go_v1_0_0_fail(self):
        make_repo(self.root, "1.0.0")
        for tag in ("typescript/v1.0.0", "go/v1.0.0"):
            with self.subTest(tag=tag):
                self.assertFails(crv.check_tag, tag, self.root, contains="outside the 0.Y.Z series")


class ZeroSeries(RepoCase):
    def test_python_v0_2_0_passes_when_files_say_0_2_0(self):
        make_repo(self.root, "0.2.0")
        self.assertIn("0.Y.Z series", crv.check_tag("python/v0.2.0", self.root))

    def test_every_language_passes(self):
        make_repo(self.root, "0.2.0")
        for tag in ("python/v0.2.0", "typescript/v0.2.0", "go/v0.2.0"):
            with self.subTest(tag=tag):
                crv.check_tag(tag, self.root)

    def test_tag_mismatch_fails(self):
        make_repo(self.root, "0.1.0")
        self.assertFails(crv.check_tag, "python/v0.2.0", self.root, contains="version files say 0.1.0")

    def test_valid_prerelease_in_0_series_passes(self):
        make_repo(self.root, "0.2.0-rc.1")
        crv.check_tag("python/v0.2.0-rc.1", self.root)

    def test_files_mode_passes(self):
        make_repo(self.root, "0.1.0")
        self.assertIn("0.1.0", crv.check_files(self.root))


class Approvals(RepoCase):
    def test_listed_approval_passes(self):
        make_repo(self.root, "1.0.1", approvals={"approvals": [APPROVAL]})
        message = crv.check_tag("python/v1.0.1", self.root)
        self.assertIn("approved by Kurt Seifried", message)
        self.assertIn(APPROVAL["reference"], message)

    def test_files_mode_passes_with_an_approval_for_that_version(self):
        make_repo(self.root, "1.0.1", approvals={"approvals": [APPROVAL]})
        self.assertIn("python/v1.0.1", crv.check_files(self.root))

    def test_approval_is_for_the_exact_tag_only(self):
        make_repo(self.root, "1.0.1", approvals={"approvals": [APPROVAL]})
        self.assertFails(crv.check_tag, "typescript/v1.0.1", self.root, contains="exact tag")
        self.assertFails(crv.check_tag, "go/v1.0.1", self.root, contains="exact tag")

    def test_approval_for_another_version_does_not_count(self):
        make_repo(self.root, "1.0.2", approvals={"approvals": [APPROVAL]})
        self.assertFails(crv.check_tag, "python/v1.0.2", self.root, contains="exact tag")
        self.assertFails(crv.check_files, self.root, contains="approves no tag")

    def test_prerelease_of_1_0_0_still_needs_approval(self):
        # 1.0.0-rc.1 sorts below 1.0.0 in SemVer but above every 0.Y.Z release.
        make_repo(self.root, "1.0.0-rc.1")
        self.assertFails(crv.check_tag, "python/v1.0.0-rc.1", self.root, contains="outside the 0.Y.Z")

    def test_major_2_and_10_need_approval(self):
        for version in ("2.0.0", "10.0.0"):
            with self.subTest(version=version):
                sub = self.root / version
                sub.mkdir()
                make_repo(sub, version)
                self.assertFails(crv.check_tag, f"python/v{version}", sub, contains="outside the 0.Y.Z")

    def test_malformed_entries_fail(self):
        bad_entries = {
            "wrong approver": dict(APPROVAL, approved_by="Someone Else"),
            "approver case": dict(APPROVAL, approved_by="kurt seifried"),
            "missing reference": {k: v for k, v in APPROVAL.items() if k != "reference"},
            "extra key": dict(APPROVAL, note="x"),
            "http reference": dict(APPROVAL, reference="http://github.com/x"),
            "relative reference": dict(APPROVAL, reference="/issues/1"),
            "javascript reference": dict(APPROVAL, reference="javascript:alert(1)"),
            "reference with space": dict(APPROVAL, reference="https://github.com/a b"),
            "empty reason": dict(APPROVAL, reason="   "),
            "bad date format": dict(APPROVAL, date="12/01/2026"),
            "impossible date": dict(APPROVAL, date="2026-02-30"),
            "non-string date": dict(APPROVAL, date=20261201),
            "bad tag": dict(APPROVAL, tag="python/1.0.1"),
            "non-semver tag": dict(APPROVAL, tag="python/v1.0"),
        }
        for name, entry in bad_entries.items():
            with self.subTest(name=name):
                sub = self.root / name.replace(" ", "-")
                sub.mkdir()
                make_repo(sub, "1.0.1", approvals={"approvals": [entry]})
                self.assertFails(crv.check_tag, "python/v1.0.1", sub)
                self.assertFails(crv.check_files, sub)

    def test_malformed_file_fails(self):
        bad_files = {
            "not json": "{approvals: []}",
            "top-level list": "[]",
            "unknown top-level key": json.dumps({"approvals": [], "approved": True}),
            "approvals not a list": json.dumps({"approvals": {}}),
            "missing approvals": json.dumps({"about": "x"}),
            "duplicate tag": json.dumps({"approvals": [APPROVAL, APPROVAL]}),
            "duplicate JSON key": (
                '{"approvals": [{"tag": "python/v1.0.1", "approved_by": "Someone Else", '
                '"approved_by": "Kurt Seifried", "date": "2026-12-01", '
                '"reference": "https://github.com/x", "reason": "r"}]}'
            ),
        }
        for name, text in bad_files.items():
            with self.subTest(name=name):
                sub = self.root / name.replace(" ", "-")
                sub.mkdir()
                make_repo(sub, "1.0.1", approvals=text)
                self.assertFails(crv.check_tag, "python/v1.0.1", sub)

    def test_malformed_file_fails_even_for_a_0_series_release(self):
        make_repo(self.root, "0.2.0", approvals="{not json")
        self.assertFails(crv.check_tag, "python/v0.2.0", self.root, contains="not valid JSON")
        self.assertFails(crv.check_files, self.root, contains="not valid JSON")


class TagSyntax(RepoCase):
    def test_invalid_tags_fail(self):
        make_repo(self.root, "0.2.0")
        for tag in (
            "v0.2.0",               # no language prefix
            "ruby/v0.2.0",          # unknown language
            "python/0.2.0",         # no v
            "python/v0.2",          # not SemVer
            "python/v0.2.0.0",
            "python/v00.2.0",       # leading zero
            "python/v0.02.0",
            "python/v0.2.0-",       # empty pre-release
            "python/v0.2.0-01",     # numeric pre-release with leading zero
            "python/v0.2.0\n",      # trailing newline
            "python/v١.2.0",   # Arabic-Indic digit one
            "python/v",
        ):
            with self.subTest(tag=tag):
                self.assertFails(crv.check_tag, tag, self.root)


class SemVer(unittest.TestCase):
    """parse_semver on its own, so a bad version fails as SemVer, not only as a mismatch."""

    def test_valid(self):
        for version, major in (("0.1.0", 0), ("1.0.0", 1), ("10.20.30", 10),
                               ("1.0.0-rc.1", 1), ("0.2.0-alpha.0+build.7", 0), ("1.0.0-0A.is.legal", 1)):
            with self.subTest(version=version):
                self.assertEqual(crv.parse_semver(version), major)

    def test_invalid(self):
        for version in ("", "1", "1.0", "1.0.0.0", "01.0.0", "1.0.0-", "1.0.0+", "1.0.0-01",
                        "1.0.0\n", " 1.0.0", "1.0.0 ", "v1.0.0", "١.0.0", "1.0.0-rc..1"):
            with self.subTest(version=version):
                self.assertFails(crv.parse_semver, version, contains="not a valid SemVer")

    assertFails = RepoCase.assertFails


class VersionFiles(RepoCase):
    def test_lockstep_break_fails(self):
        for key in ("python", "ts_pkg", "ts_src", "go"):
            with self.subTest(file=key):
                sub = self.root / key
                sub.mkdir()
                make_repo(sub, "0.2.0", overrides={key: "0.1.0"})
                self.assertFails(crv.check_tag, "python/v0.2.0", sub, contains="out of lockstep")
                self.assertFails(crv.check_files, sub, contains="out of lockstep")

    def test_invalid_semver_in_files_fails(self):
        for version in ("1.0", "0.2.0.0"):
            with self.subTest(version=version):
                sub = self.root / version
                sub.mkdir()
                make_repo(sub, version)
                self.assertFails(crv.check_files, sub, contains="not a valid SemVer")
                self.assertFails(crv.check_tag, f"python/v{version}", sub, contains="not a valid SemVer")

    def test_pyproject_static_version_must_match(self):
        make_repo(self.root, "0.2.0", pyproject='[project]\nname = "csa-secid"\nversion = "1.0.0"\n')
        self.assertFails(crv.check_tag, "python/v0.2.0", self.root, contains="out of lockstep")

    def test_pyproject_static_version_that_matches_passes(self):
        make_repo(self.root, "0.2.0", pyproject='[project]\nname = "csa-secid"\nversion = "0.2.0"\n')
        crv.check_tag("python/v0.2.0", self.root)

    def test_pyproject_version_in_another_table_is_ignored(self):
        pyproject = (
            '[project]\nname = "csa-secid"\ndynamic = ["version"]\n\n'
            '[[tool.other]]\nversion = "9.9.9"\n'
        )
        make_repo(self.root, "0.2.0", pyproject=pyproject)
        crv.check_tag("python/v0.2.0", self.root)

    def test_pyproject_without_version_fails(self):
        make_repo(self.root, "0.2.0", pyproject='[project]\nname = "csa-secid"\n')
        self.assertFails(crv.check_files, self.root, contains="neither")

    def test_two_version_assignments_fail(self):
        make_repo(self.root, "0.2.0")
        path = self.root / "python" / "secid_client.py"
        path.write_text(path.read_text() + '__version__ = "1.0.0"\n')
        self.assertFails(crv.check_files, self.root, contains="exactly one")

    def test_missing_version_file_fails(self):
        make_repo(self.root, "0.2.0")
        (self.root / "go" / "secid.go").unlink()
        self.assertFails(crv.check_files, self.root, contains="missing")


class CommandLine(RepoCase):
    """Run the script the way release.yml does: python3 -I, exit codes."""

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPT), *args],
            capture_output=True, text=True, timeout=60, check=False,
        )

    def test_exit_codes(self):
        incident = self.root / "incident"
        incident.mkdir()
        make_repo(incident, "1.0.0")
        refused = self.run_script("--tag", "python/v1.0.0", "--repo", str(incident))
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn("outside the 0.Y.Z series", refused.stderr)

        ok = self.root / "ok"
        ok.mkdir()
        make_repo(ok, "0.2.0")
        passed = self.run_script("--tag", "python/v0.2.0", "--repo", str(ok))
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertIn("OK:", passed.stdout)

        approved = self.root / "approved"
        approved.mkdir()
        make_repo(approved, "1.0.1", approvals={"approvals": [APPROVAL]})
        passed = self.run_script("--tag", "python/v1.0.1", "--repo", str(approved))
        self.assertEqual(passed.returncode, 0, passed.stderr)

    def test_usage_error_exits_2(self):
        self.assertEqual(self.run_script().returncode, 2)
        self.assertEqual(self.run_script("--tag", "python/v0.1.0", "--files").returncode, 2)


class ThisRepository(unittest.TestCase):
    """The checked-in version files and RELEASE-APPROVALS.json pass files mode."""

    def test_repository_passes_files_mode(self):
        crv.check_files(crv.REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
