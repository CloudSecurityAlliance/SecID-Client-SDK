#!/usr/bin/env python3
"""Unit tests for check_release_version.py. Stdlib unittest; Python 3.11+.

Run from anywhere:

    python3 -I scripts/test_check_release_version.py -v

Every case builds a throwaway fixture repository in a fresh temporary
directory. No real tags are created or read.
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

if sys.version_info < (3, 11):
    sys.exit("check_release_version.py and its tests need Python 3.11 or newer (tomllib)")

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


BUILD_SYSTEM = '[build-system]\nrequires = ["hatchling>=1.27"]\nbuild-backend = "hatchling.build"\n\n'
DYNAMIC_PYPROJECT = (
    BUILD_SYSTEM
    + '[project]\nname = "csa-secid"\ndynamic = ["version"]  # read from __version__\n\n'
    + '[tool.hatch.version]\npath = "secid_client.py"\n'
)


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
        DYNAMIC_PYPROJECT
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
        pyproject = DYNAMIC_PYPROJECT + '\n[[tool.other]]\nversion = "9.9.9"\n'

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


class DynamicVersionSource(RepoCase):
    """P2-1 (a): with dynamic = ["version"], check where Hatchling actually reads it."""

    def test_divergent_hatch_path_fails(self):
        # Codex's reproduction: Hatch reads another file that says 1.0.1, while
        # every checked file says 0.1.0 and the approvals file is empty.
        pyproject = DYNAMIC_PYPROJECT.replace('path = "secid_client.py"', 'path = "_version.py"')
        make_repo(self.root, "0.1.0", approvals={"approvals": []}, pyproject=pyproject)
        (self.root / "python" / "_version.py").write_text('__version__ = "1.0.1"\n')
        self.assertFails(crv.check_tag, "python/v0.1.0", self.root, contains="[tool.hatch.version]")
        self.assertFails(crv.check_files, self.root, contains="[tool.hatch.version]")

    def test_hatch_reading_a_different_line_fails(self):
        # Hatchling's default pattern is case-insensitive and takes the first
        # match, so an earlier `version = "1.0.1"` line is what it would build.
        make_repo(self.root, "0.1.0")
        path = self.root / "python" / "secid_client.py"
        path.write_text('version = "1.0.1"\n' + path.read_text())
        self.assertFails(crv.check_tag, "python/v0.1.0", self.root, contains="out of lockstep")

    def test_single_quoted_version_is_not_silently_accepted(self):
        # Hatchling would read 'v0.1.0' as 0.1.0; the lockstep reader requires
        # the double-quoted form, so this fails loudly instead of passing.
        make_repo(self.root, "0.1.0")
        path = self.root / "python" / "secid_client.py"
        path.write_text(path.read_text().replace('__version__ = "0.1.0"', "__version__ = 'v0.1.0'"))
        self.assertFails(crv.check_files, self.root, contains="exactly one")

    def test_other_hatch_version_settings_fail(self):
        variants = {
            "custom pattern": '[tool.hatch.version]\npath = "secid_client.py"\npattern = "X = (?P<version>.+)"\n',
            "other source": '[tool.hatch.version]\nsource = "vcs"\n',
            "explicit source": '[tool.hatch.version]\nsource = "regex"\npath = "secid_client.py"\n',
            "missing table": "",
            "dotted path": '[tool.hatch]\nversion.path = "_version.py"\n',
        }
        base = BUILD_SYSTEM + '[project]\nname = "csa-secid"\ndynamic = ["version"]\n\n'
        for name, table in variants.items():
            with self.subTest(name=name):
                sub = self.root / name.replace(" ", "-")
                sub.mkdir()
                make_repo(sub, "0.1.0", pyproject=base + table)
                self.assertFails(crv.check_files, sub, contains="[tool.hatch.version]")

    def test_other_backend_fails(self):
        pyproject = DYNAMIC_PYPROJECT.replace("hatchling.build", "setuptools.build_meta")
        make_repo(self.root, "0.1.0", pyproject=pyproject)
        self.assertFails(crv.check_files, self.root, contains="build-backend")

    def test_metadata_hooks_fail(self):
        pyproject = DYNAMIC_PYPROJECT + '\n[tool.hatch.metadata.hooks.custom]\npath = "hook.py"\n'
        make_repo(self.root, "0.1.0", pyproject=pyproject)
        self.assertFails(crv.check_files, self.root, contains="hooks")

    def test_invalid_toml_fails(self):
        make_repo(self.root, "0.1.0", pyproject="[project\nname = ")
        self.assertFails(crv.check_files, self.root, contains="not valid TOML")


def write_dist(dist: pathlib.Path, wheel_version: str, sdist_version: str,
               name: str = "csa-secid", extra: str | None = None) -> None:
    """Write a minimal wheel and sdist whose metadata says the given versions."""
    dist.mkdir(parents=True)
    norm = name.replace("-", "_")
    meta = "Metadata-Version: 2.4\nName: {n}\nVersion: {v}\nSummary: x\n\nlong description\nVersion: 9.9.9\n"
    with zipfile.ZipFile(dist / f"{norm}-{wheel_version}-py3-none-any.whl", "w") as whl:
        whl.writestr("secid_client.py", "")
        whl.writestr(f"{norm}-{wheel_version}.dist-info/METADATA", meta.format(n=name, v=wheel_version))
    data = meta.format(n=name, v=sdist_version).encode()
    with tarfile.open(dist / f"{norm}-{sdist_version}.tar.gz", "w:gz") as sdist:
        info = tarfile.TarInfo(f"{norm}-{sdist_version}/PKG-INFO")
        info.size = len(data)
        sdist.addfile(info, io.BytesIO(data))
    if extra:
        (dist / extra).write_text("x")


def write_npm_pack(pack: pathlib.Path, version: str, name: str = "@cloudsecurityalliance/secid",
                   count: int = 1) -> None:
    pack.mkdir(parents=True)
    for index in range(count):
        data = json.dumps({"name": name, "version": version}).encode()
        with tarfile.open(pack / f"pkg-{index}.tgz", "w:gz") as tgz:
            info = tarfile.TarInfo("package/package.json")
            info.size = len(data)
            tgz.addfile(info, io.BytesIO(data))


class BuiltArtifacts(RepoCase):
    """P2-1 (b): the packages actually built must carry the tag's version."""

    def setUp(self) -> None:
        super().setUp()
        make_repo(self.root, "0.2.0")

    def test_matching_python_dist_passes(self):
        write_dist(self.root / "dist", "0.2.0", "0.2.0")
        self.assertIn("csa-secid 0.2.0", crv.check_python_dist("python/v0.2.0", self.root / "dist", self.root))

    def test_python_dist_version_mismatch_fails(self):
        for wheel, sdist in (("1.0.1", "0.2.0"), ("0.2.0", "1.0.1")):
            with self.subTest(wheel=wheel, sdist=sdist):
                dist = self.root / f"dist-{wheel}-{sdist}"
                write_dist(dist, wheel, sdist)
                self.assertFails(crv.check_python_dist, "python/v0.2.0", dist, self.root, contains="says version")

    def test_python_dist_wrong_name_fails(self):
        write_dist(self.root / "dist", "0.2.0", "0.2.0", name="other-pkg")
        self.assertFails(crv.check_python_dist, "python/v0.2.0", self.root / "dist", self.root, contains="names the package")

    def test_python_dist_must_be_one_wheel_and_one_sdist(self):
        write_dist(self.root / "dist", "0.2.0", "0.2.0", extra="stale-1.0.0.whl")
        self.assertFails(crv.check_python_dist, "python/v0.2.0", self.root / "dist", self.root, contains="exactly one wheel")
        (self.root / "empty").mkdir()
        self.assertFails(crv.check_python_dist, "python/v0.2.0", self.root / "empty", self.root, contains="exactly one wheel")

    def test_python_dist_needs_a_python_tag(self):
        write_dist(self.root / "dist", "0.2.0", "0.2.0")
        self.assertFails(crv.check_python_dist, "typescript/v0.2.0", self.root / "dist", self.root, contains="python/")

    def test_matching_npm_pack_passes(self):
        write_npm_pack(self.root / "pack", "0.2.0")
        self.assertIn("0.2.0", crv.check_npm_pack("typescript/v0.2.0", self.root / "pack", self.root))

    def test_npm_pack_mismatch_fails(self):
        write_npm_pack(self.root / "pack", "1.0.1")
        self.assertFails(crv.check_npm_pack, "typescript/v0.2.0", self.root / "pack", self.root, contains="says version")

    def test_npm_pack_wrong_name_fails(self):
        write_npm_pack(self.root / "pack", "0.2.0", name="secid")
        self.assertFails(crv.check_npm_pack, "typescript/v0.2.0", self.root / "pack", self.root, contains="names the package")

    def test_npm_pack_must_be_one_tarball(self):
        write_npm_pack(self.root / "pack", "0.2.0", count=2)
        self.assertFails(crv.check_npm_pack, "typescript/v0.2.0", self.root / "pack", self.root, contains="exactly one .tgz")

    def test_npm_pack_needs_a_typescript_tag(self):
        write_npm_pack(self.root / "pack", "0.2.0")
        self.assertFails(crv.check_npm_pack, "python/v0.2.0", self.root / "pack", self.root, contains="typescript/")


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
        self.assertEqual(self.run_script("--files", "--dist", "x").returncode, 2)
        self.assertEqual(self.run_script("--tag", "python/v0.1.0", "--dist", "x", "--npm-pack", "y").returncode, 2)

    def test_artifact_mode_refuses_a_divergent_build(self):
        make_repo(self.root, "0.2.0")
        write_dist(self.root / "dist", "1.0.1", "1.0.1")
        refused = self.run_script("--tag", "python/v0.2.0", "--dist", str(self.root / "dist"), "--repo", str(self.root))
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn("says version '1.0.1'", refused.stderr)


class ThisRepository(unittest.TestCase):
    """The checked-in version files and RELEASE-APPROVALS.json pass files mode."""

    def test_repository_passes_files_mode(self):
        crv.check_files(crv.REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
