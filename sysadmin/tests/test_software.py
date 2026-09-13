"""Safety and state-based verification regression tests (no package mutation)."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import test_lifecycle
from ai_sysadmin import Controller, upgrade_candidates


class SoftwareTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_lifecycle.LifecycleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.c = self.fixture.c
        self.root = Path(self.fixture.temp.name)
        self.c.config["inventory"] = {"roots": [str(self.root / "opt")]}
        self.c.config["splunk"] = {"home": str(self.root / "opt/splunk")}
        self.inventory = {"apt_packages": {"example": "1.2.3"}, "extra": [],
                          "errors": [], "package_version_conflicts": []}
        self.healthy = dict(self.fixture.healthy, software_inventory=copy.deepcopy(self.inventory))
        self.simulation = "Inst example [1.2.3] (1.2.4 Ubuntu:24.04/noble-updates [amd64])\n"
        self.ok = {"returncode": 0, "stdout": "", "stderr": ""}

    def inventory_commands(self, action, argv, *args, **kwargs):
        result = self.ok.copy()
        if action == "inventory_dpkg":
            result["stdout"] = "example\t1.2.3\tinstalled\nsplunk\t9.0.9+build\tinstalled\nremoved\t1.0\tconfig-files\n"
        return result

    def test_inventory_reads_splunk_and_python_metadata_without_executing_them(self):
        manifest = self.root / "opt/splunk/etc/splunk.version"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("VERSION=9.3.14\nPRODUCT=splunk\n")
        metadata = self.root / "opt/litellm/venv/lib/python3.12/site-packages/litellm-1.0.dist-info/METADATA"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("Name: litellm\nVersion: 1.63.2\n\nDescription\n")
        self.c.command = Mock(side_effect=self.inventory_commands)
        with patch("ai_sysadmin.shutil.which", return_value=None):
            inventory = self.c.software_inventory()
        found = {(i["name"], i["version"]) for i in inventory["extra"]}
        self.assertIn(("splunk", "9.3.14"), found)
        self.assertIn(("litellm", "1.63.2"), found)
        self.assertNotIn("removed", inventory["apt_packages"])
        self.assertEqual(inventory["package_version_conflicts"][0]["package_version"], "9.0.9+build")
        self.assertEqual([call.args[1][0] for call in self.c.command.call_args_list], ["dpkg-query", "dpkg"])
        events = [json.loads(line) for line in (self.c.logs / "anomalies.jsonl").read_text().splitlines()]
        self.assertTrue(any("versions disagree" in e["message"] for e in events))

    def test_unknown_installation_is_reported_without_guessing_version(self):
        (self.root / "opt/custom-app").mkdir(parents=True)
        (self.root / "opt/custom-app/program").write_text("unknown binary")
        self.c.command = Mock(side_effect=self.inventory_commands)
        with patch("ai_sysadmin.shutil.which", return_value=None):
            inventory = self.c.software_inventory()
        self.assertEqual(inventory["extra"][0]["version"], "unknown")
        self.assertIn("version identification", (self.c.logs / "anomalies.jsonl").read_text())

    def test_broken_package_database_is_an_inspection_error(self):
        self.c.command = Mock(side_effect=[
            dict(self.ok, stdout="example\t1.2.3\tinstalled\n"),
            dict(self.ok, stdout="The following packages are only half configured:\n example\n")])
        with patch("ai_sysadmin.shutil.which", return_value=None):
            inventory = self.c.software_inventory()
        self.assertIn("Package database needs attention", inventory["errors"])

    def test_snap_empty_is_valid_but_timeout_is_not(self):
        for result, errors in ((dict(self.ok, returncode=1, stderr="No snaps are installed yet."), False),
                               (dict(self.ok, returncode=124), True)):
            self.c.command = Mock(side_effect=[dict(self.ok, stdout="example\t1.2.3\tinstalled\n"), self.ok, result])
            with patch("ai_sysadmin.shutil.which", side_effect=lambda name: "/usr/bin/snap" if name == "snap" else None):
                inventory = self.c.software_inventory()
            self.assertEqual(bool(inventory["errors"]), errors)

    def test_major_epoch_ambiguous_new_install_and_removal_are_rejected(self):
        for line in ("Inst example [1.2] (2.0 repo [amd64])",
                     "Inst example [1:1.2] (2:1.3 repo [amd64])",
                     "Inst example [20250101] (20260101 repo [amd64])",
                     "Inst example (1.2 repo [amd64])",
                     "Inst unparseable",
                     "Remv example [1.2]", "Purg example [1.2]"):
            with self.subTest(line=line):
                self.assertTrue(upgrade_candidates(line)[1])

    def test_same_major_and_security_revision_allowed(self):
        for old, new in (("1:9.6p1-3ubuntu13.1", "1:9.6p1-3ubuntu13.2"),
                         ("1.2.3", "1.4.0"), ("20250101-1", "20250101-1ubuntu0.1")):
            self.assertFalse(upgrade_candidates(f"Inst example [{old}] ({new} repo [amd64])")[1])

    def test_exact_transaction_is_pinned_and_dependency_change_refused(self):
        for second, expected_error in ((self.simulation, False),
                                       (self.simulation + "Inst dependency (2.0 repo [amd64])\n", True)):
            self.c.command = Mock(side_effect=[dict(self.ok, stdout=self.simulation), self.ok,
                                               dict(self.ok, stdout=second)])
            argv, packages, errors = Controller.approved_upgrade(self.c, self.healthy)
            self.assertEqual(bool(errors), expected_error)
            self.assertIn("example=1.2.4", argv)
            self.assertIn("--no-remove", argv)
            self.assertIn("--only-upgrade", argv)
            self.assertEqual(packages[0]["after"], "1.2.4")

    def test_downgrade_is_refused(self):
        self.c.command = Mock(side_effect=[dict(self.ok, stdout=self.simulation), dict(self.ok, returncode=1)])
        argv, _, errors = Controller.approved_upgrade(self.c, self.healthy)
        self.assertFalse(argv)
        self.assertTrue(errors)
        self.assertEqual(self.c.command.call_count, 2)

    def test_conflicting_vendor_version_cannot_be_upgraded(self):
        inspection = copy.deepcopy(self.healthy)
        inspection["software_inventory"]["package_version_conflicts"] = [{"name": "splunk"}]
        self.c.command = Mock(side_effect=[dict(self.ok, stdout="Inst splunk [9.0.9] (9.0.10 repo [amd64])"), self.ok])
        argv, _, errors = Controller.approved_upgrade(self.c, inspection)
        self.assertFalse(argv)
        self.assertTrue(any("Conflicting" in error for error in errors))

    def test_failed_or_empty_simulation(self):
        for result, blocked in ((dict(self.ok, returncode=100), True), (self.ok, False)):
            self.c.command = Mock(return_value=result)
            argv, packages, errors = Controller.approved_upgrade(self.c, self.healthy)
            self.assertFalse(argv)
            self.assertFalse(packages)
            self.assertEqual(bool(errors), blocked)

    def run_maintenance(self, actual_version):
        self.c.dry_run = False
        self.c.inspect = Mock(return_value=copy.deepcopy(self.healthy))
        self.assertEqual(self.c.prepare(), 0)
        post = copy.deepcopy(self.healthy)
        post["software_inventory"]["apt_packages"]["example"] = actual_version
        self.c.inspect = Mock(side_effect=[copy.deepcopy(self.healthy), post])
        self.c.approved_upgrade = Controller.approved_upgrade.__get__(self.c)

        def execute(action, argv, *args, **kwargs):
            result = self.ok.copy()
            if action in ("simulate_refreshed_upgrade", "simulate_exact_upgrade"):
                result["stdout"] = self.simulation
            return result
        self.c.command = Mock(side_effect=execute)
        return self.c.maintain()

    def test_successful_command_with_wrong_installed_version_fails_change(self):
        self.assertEqual(self.run_maintenance("1.2.3"), 1)
        text = self.fixture.record().read_text()
        self.assertIn("Status: FAILED", text)
        self.assertIn("Expected version not installed", text)

    def test_verified_upgrade_closes_and_records_actual_version_delta(self):
        self.assertEqual(self.run_maintenance("1.2.4"), 0)
        text = self.fixture.record().read_text()
        self.assertIn("Status: CLOSED", text)
        self.assertIn('"before": "1.2.3", "after": "1.2.4"', text)
        upgrades = [call for call in self.c.command.call_args_list if call.args[0] == "apt_upgrade"]
        self.assertEqual(len(upgrades), 1)
        self.assertIn("example=1.2.4", upgrades[0].args[1])

    def test_removal_and_external_software_drift_fail_verification(self):
        pre = copy.deepcopy(self.healthy)
        pre["software_inventory"]["extra"] = [{"name": "splunk", "version": "9.3.14", "location": "/opt/splunk"}]
        post = copy.deepcopy(self.healthy)
        post["software_inventory"]["apt_packages"] = {}
        _, errors = self.c.verify_software(pre, post, [])
        self.assertTrue(any("disappeared" in error for error in errors))
        self.assertTrue(any("outside APT changed" in error for error in errors))

    def test_ai_cannot_approve_major_upgrade(self):
        inspection = dict(self.healthy, package_policy_errors=["Major upgrade refused"])
        self.c.config["ai"] = {"required": True, "command": ["/trusted/planner"]}
        with patch("ai_sysadmin.subprocess.run", return_value=Mock(stdout='{"proceed":true,"reasoning":"yes"}')):
            plan = self.c.plan(inspection)
        self.assertIn("Major upgrade refused", plan["blocked_reasons"])
        self.assertEqual([a["id"] for a in plan["actions"]], ["verify"])

