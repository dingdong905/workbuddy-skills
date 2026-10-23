import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("release", Path(__file__).parents[1] / "skill_release.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source, self.runtime, self.backup = root / "source", root / "runtime", root / "backups"
        for p in (self.source / "demo" / "references", self.runtime):
            p.mkdir(parents=True)
        (self.source / "demo" / "SKILL.md").write_text("source")
        (self.source / "demo" / "references" / "rules.md").write_text("rules")
        (self.source / "LICENSE").write_text("MIT")
        self.report = root / "report.json"
        m.write_new(self.report, {"schema_version": 1, "platform": "codex", "kind": "structure",
                                 "status": "pass", "subjects": [m.subject(self.source, "demo")], "inputs": []})

    def install(self, expected="absent"):
        return m.install(self.source, self.runtime, self.backup, "codex", "demo", expected, [self.report])

    def test_resource_and_filename_change_digest(self):
        old = m.digest(self.source / "demo")
        (self.source / "demo" / "references" / "rules.md").write_text("new")
        self.assertNotEqual(old, m.digest(self.source / "demo"))
        self.assertFalse(m.report_applicable(m.read(self.report), self.source, "demo", "codex"))

    def test_raw_bytes_not_newline_normalized(self):
        p = self.source / "demo" / "SKILL.md"
        p.write_bytes(b"x\n")
        old = m.digest(p.parent)
        p.write_bytes(b"x\r\n")
        self.assertNotEqual(old, m.digest(p.parent))

    def test_new_file_invalidates_report(self):
        (self.source / "demo" / "extra.txt").write_text("new")
        self.assertFalse(m.report_applicable(m.read(self.report), self.source, "demo", "codex"))

    def test_test_input_change_invalidates_report(self):
        p = self.source / "cases.json"
        p.write_text("[]")
        r = m.read(self.report)
        r["inputs"] = m.inputs(self.source, ["cases.json"])
        self.assertTrue(m.report_applicable(r, self.source, "demo", "codex"))
        p.write_text("[1]")
        self.assertFalse(m.report_applicable(r, self.source, "demo", "codex"))

    def test_all_subjects_invalidate_integration_report(self):
        (self.source / "upstream").mkdir()
        (self.source / "upstream" / "SKILL.md").write_text("v1")
        report = m.read(self.report)
        report["subjects"].append(m.subject(self.source, "upstream"))
        self.assertTrue(m.report_applicable(report, self.source, "demo", "codex"))
        (self.source / "upstream" / "SKILL.md").write_text("v2")
        self.assertFalse(m.report_applicable(report, self.source, "demo", "codex"))

    def test_audit_link_is_unverifiable_not_missing(self):
        with patch.object(m, "linked", side_effect=lambda p: Path(p) == self.source / "demo"):
            result = m.audit(self.source, self.runtime, "codex")
        self.assertEqual(result["rows"][0]["installation"], "unverifiable")
        self.assertTrue(result["rows"][0]["limits"])

    def test_platform_mismatch_rejected(self):
        self.assertFalse(m.report_applicable(m.read(self.report), self.source, "demo", "workbuddy"))

    def test_states(self):
        (self.runtime / "private").mkdir()
        (self.runtime / "private" / "SKILL.md").write_text("runtime only")
        states = {r["skill"]: r["installation"] for r in m.audit(self.source, self.runtime, "codex")["rows"]}
        self.assertEqual(states, {"demo": "not_installed", "private": "runtime_only"})
        self.install()
        self.assertEqual(next(r for r in m.audit(self.source, self.runtime, "codex")["rows"] if r["skill"] == "demo")["installation"], "same_version")
        (self.runtime / "demo" / "extra").write_text("old")
        self.assertEqual(next(r for r in m.audit(self.source, self.runtime, "codex")["rows"] if r["skill"] == "demo")["installation"], "drift")

    def test_backup_and_no_stale_files(self):
        (self.runtime / "demo").mkdir()
        (self.runtime / "demo" / "obsolete.txt").write_text("must survive in backup")
        old = m.digest(self.runtime / "demo")
        receipt = self.install(old)
        self.assertFalse((self.runtime / "demo" / "obsolete.txt").exists())
        self.assertEqual((Path(receipt["backup"]) / "obsolete.txt").read_text(), "must survive in backup")
        self.assertEqual(m.digest(self.runtime / "demo"), m.digest(self.source / "demo"))
        self.assertTrue((Path(receipt["receipt"]).parent / "provenance" / "LICENSE").exists())

    def test_drift_requires_exact_precondition(self):
        (self.runtime / "demo").mkdir()
        (self.runtime / "demo" / "SKILL.md").write_text("do not overwrite")
        with self.assertRaisesRegex(ValueError, "expected digest"):
            self.install()

    def test_missing_report_rejected(self):
        with self.assertRaisesRegex(ValueError, "structure"):
            m.install(self.source, self.runtime, self.backup, "codex", "demo", "absent", [])

    def test_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, "backup"):
            m.install(self.source, self.runtime, self.runtime / "backups", "codex", "demo", "absent", [self.report])

    def test_traversal_rejected(self):
        with self.assertRaises(ValueError):
            m.subject(self.source, "../demo")

    def test_failure_rolls_back(self):
        target = self.runtime / "demo"
        target.mkdir()
        (target / "old").write_text("old")
        old = m.digest(target)
        real = m.digest
        def changed(path):
            result = real(path)
            if Path(path) == target and (target / "SKILL.md").exists():
                return "mismatch"
            return result
        with patch.object(m, "digest", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "post-install"):
                self.install(old)
        self.assertEqual(real(target), old)
        self.assertEqual(len(list(self.runtime.parent.glob(".skill-release-recovery/*/failed-new-demo"))), 1)

    def test_old_rename_failure_keeps_original(self):
        target = self.runtime / "demo"
        target.mkdir()
        (target / "old").write_text("original")
        old = m.digest(target)
        real_rename = Path.rename
        def fail_old(path, dest):
            if path == target:
                raise PermissionError("simulated locked runtime")
            return real_rename(path, dest)
        with patch.object(Path, "rename", fail_old):
            with self.assertRaises(PermissionError):
                self.install(old)
        self.assertEqual(m.digest(target), old)
        self.assertFalse(list(self.runtime.parent.glob(".skill-release-recovery/*/failed-new-*")))

    def test_cross_volume_renames_never_required(self):
        target = self.runtime / "demo"
        target.mkdir()
        (target / "old").write_text("original")
        old = m.digest(target)
        real_rename = Path.rename
        def only_same_parent(path, dest):
            if Path(dest).is_relative_to(self.backup):
                raise OSError("simulated cross-device rename")
            return real_rename(path, dest)
        with patch.object(Path, "rename", only_same_parent):
            receipt = self.install(old)
        self.assertEqual(m.digest(Path(receipt["backup"])), old)
        self.assertEqual(m.digest(target), m.digest(self.source / "demo"))

    def test_validation_detects_mutating_command(self):
        out = Path(self.tmp.name) / "validation.json"
        command = [sys.executable, "-B", "-c", "from pathlib import Path; Path('demo/SKILL.md').write_text('changed')"]
        r = m.verify(self.source, "codex", ["demo"], [], "unit", command, out)
        self.assertEqual(r["status"], "fail")
        self.assertFalse(r["content_unchanged"])

    def test_report_not_overwritten(self):
        with self.assertRaises(FileExistsError):
            m.write_new(self.report, {})


if __name__ == "__main__":
    unittest.main()
