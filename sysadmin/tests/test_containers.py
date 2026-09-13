"""Container maintenance tests: commands are mocked; no live containers are changed."""
import copy
import io
import json
from pathlib import Path
import tarfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from unittest.mock import Mock, patch

import test_lifecycle
from container_maintenance import ContainerMaintenance, VERSION_LABEL, DEPENDENCY_LABEL, fingerprint, version_errors
from render_deployment import render


class ContainerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_lifecycle.LifecycleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.c = self.fixture.c
        self.root = Path(self.fixture.temp.name)
        compose = self.root / "compose.json"
        compose.write_text('{"services":{"app":{"image":"example/app:latest"}}}')
        self.service = {"name": "app", "project": "example", "service": "app",
                        "compose_files": [str(compose)], "image": "example/app:latest",
                        "hold": False, "health_url": "http://127.0.0.1:1234/ready",
                        "stability_seconds": 0, "maximum_backup_bytes": 1024}
        self.c.config["containers"] = {"enabled": True, "services": [self.service]}
        self.d = self.c.containers = ContainerMaintenance(self.c)
        self.old_id, self.new_id = "sha256:" + "a" * 64, "sha256:" + "b" * 64
        self.old_ref, self.new_ref = "example/app@sha256:" + "c" * 64, "example/app@sha256:" + "d" * 64
        self.current = {"name": "app", "id": "container-id", "image_id": self.old_id,
                        "digests": [self.old_ref], "versions": {VERSION_LABEL: "2.3.4"},
                        "project": "example", "service": "app", "compose_hash": "config-hash",
                        "runtime_hash": "runtime-hash", "running": True, "health": "not_configured",
                        "restart_count": 0, "platform": "linux/amd64",
                        "mounts": [{"Type": "volume", "Name": "data", "Source": "/volume/data",
                                    "Destination": "/data", "RW": True}]}
        self.target = {"image": self.new_ref, "image_id": self.new_id, "versions": {VERSION_LABEL: "2.3.5"}}
        self.model = {"services": {"app": {"image": "example/app:latest"}}}
        self.d.compose_state = Mock(return_value=(self.model, "config-hash"))
        self.d.candidate = Mock(return_value=self.target)
        self.d.current = Mock(side_effect=lambda name: copy.deepcopy(self.current))

    def plan(self):
        return self.d.plan({"items": [self.current]})

    def test_only_same_major_non_downgrade_versions_allowed(self):
        for old, new, blocked in (("2.3.4", "2.4.0", False), ("2.3.4", "3.0.0", True),
                                  ("2.3.4", "2.3.3", True), ("unknown", "2.3.4", True)):
            self.assertEqual(bool(version_errors({VERSION_LABEL: old}, {VERSION_LABEL: new})), blocked)
        old = {VERSION_LABEL: "2.3.4", DEPENDENCY_LABEL: "24.1.0-alpine"}
        new = {VERSION_LABEL: "2.4.0", DEPENDENCY_LABEL: "26.0.0-alpine"}
        self.assertTrue(version_errors(old, new))
        self.assertTrue(version_errors({}, new))

    def test_plan_records_exact_digest_and_before_state(self):
        updates, deferred = self.plan()
        self.assertFalse(deferred)
        self.assertEqual(updates[0]["image"], self.new_ref)
        self.assertEqual(updates[0]["policy_hash"], fingerprint(self.service))
        self.assertEqual(updates[0]["before_image"], self.old_ref)

    def test_held_container_never_queries_registry(self):
        self.service["hold"] = True
        self.assertEqual(self.plan(), ([], []))
        self.d.candidate.assert_not_called()

    def test_current_digest_does_not_create_update(self):
        self.target["image_id"] = self.old_id
        self.assertEqual(self.plan(), ([], []))

    def test_major_base_runtime_upgrade_is_deferred(self):
        self.current["versions"][DEPENDENCY_LABEL] = "24.1.0-alpine"
        self.target["versions"][DEPENDENCY_LABEL] = "26.0.0-alpine"
        updates, deferred = self.plan()
        self.assertFalse(updates)
        self.assertIn("major change", deferred[0]["reason"])

    def test_configuration_drift_and_missing_health_gate_are_deferred(self):
        self.current["compose_hash"] = "unexpected"
        self.assertTrue(self.plan()[1])
        self.current["compose_hash"] = "config-hash"
        del self.service["health_url"]
        self.assertTrue(self.plan()[1])

    def test_shared_writable_data_is_refused(self):
        other = dict(self.current, name="other")
        updates, deferred = self.d.plan({"items": [self.current, other]})
        self.assertFalse(updates)
        self.assertIn("shared", deferred[0]["reason"])

    def test_hold_added_after_prepare_blocks_execution(self):
        updates, _ = self.plan()
        self.service["hold"] = True
        self.assertTrue(self.d.validate(updates))

    def test_container_replaced_after_prepare_blocks_execution(self):
        updates, _ = self.plan()
        self.current["id"] = "unexpected"
        self.assertTrue(self.d.validate(updates))

    def test_dry_run_never_pulls_stops_or_backs_up(self):
        updates, _ = self.plan()
        self.d.command = Mock()
        self.d.archive = Mock()
        result = self.d.apply(updates, "CHG-20260913")
        self.assertTrue(result[0]["simulated"])
        self.d.command.assert_not_called()
        self.d.archive.assert_not_called()

    def test_verified_update_backs_up_before_recreating_and_is_repeatable(self):
        updates, _ = self.plan()
        self.c.dry_run = False
        actions = []

        def execute(action, argv, **kwargs):
            actions.append(action)
            if action == "container_stop_for_backup":
                self.current["running"] = False
            if action == "container_recreate":
                self.current["image_id"] = self.new_id
                self.current["running"] = True
            return ""
        self.d.command = Mock(side_effect=execute)
        self.d.json_command = Mock(return_value=[{"Id": self.new_id, "Config": {"Labels": self.target["versions"]}}])
        self.d.readiness = Mock(side_effect=lambda *args: copy.deepcopy(self.current))
        self.d.archive = Mock(side_effect=lambda *args: actions.append("archive") or {"sha256": "verified"})
        result = self.d.apply(updates, "CHG-20260913")
        self.assertEqual(result[0]["returncode"], 0)
        self.assertLess(actions.index("archive"), actions.index("container_recreate"))
        self.assertEqual(json.loads(self.d.override(self.service).read_text())["services"]["app"]["image"], self.new_ref)
        actions.clear()
        again = self.d.apply(updates, "CHG-20260913")
        self.assertTrue(again[0]["skipped"])
        self.assertFalse(actions)

    def test_backup_failure_resumes_original_without_replacement(self):
        updates, _ = self.plan()
        self.c.dry_run = False

        def execute(action, argv, **kwargs):
            if action == "container_stop_for_backup":
                self.current["running"] = False
            return ""
        self.d.command = Mock(side_effect=execute)
        self.d.json_command = Mock(return_value=[{"Id": self.new_id, "Config": {"Labels": self.target["versions"]}}])
        self.d.readiness = Mock(return_value=self.current)
        self.d.archive = Mock(side_effect=RuntimeError("backup failed"))
        self.c.command = Mock(return_value={"returncode": 0})
        result = self.d.apply(updates, "CHG-20260913")
        self.assertEqual(result[0]["returncode"], 1)
        self.assertFalse(result[0]["replacement_started"])
        self.assertFalse(any(c.args[0] == "container_recreate" for c in self.d.command.call_args_list))
        self.assertEqual(self.c.command.call_args.args[0], "container_resume_after_backup_failure")

    def test_wrong_pulled_digest_never_stops_service(self):
        updates, _ = self.plan()
        self.c.dry_run = False
        self.d.command = Mock(return_value="")
        self.d.json_command = Mock(return_value=[{"Id": self.old_id}])
        result = self.d.apply(updates, "CHG-20260913")
        self.assertEqual(result[0]["returncode"], 1)
        self.assertFalse(any(c.args[0] == "container_stop_for_backup" for c in self.d.command.call_args_list))

    def test_sensitive_command_results_never_enter_audit(self):
        secret = '{"environment":{"PASSWORD":"do-not-log-this"}}'
        with patch("ai_sysadmin.subprocess.run", return_value=Mock(returncode=0, stdout=secret, stderr=secret)):
            result = self.c.command("compose", ["docker", "compose", "config"], sensitive=True)
        self.assertEqual(result["stdout"], secret)
        audit = (self.c.logs / "audit.jsonl").read_text()
        self.assertNotIn("do-not-log-this", audit)
        self.assertIn("stdout_sha256", audit)

    def test_registry_platform_digest_and_version_are_taken_from_pinned_image(self):
        self.d.candidate = ContainerMaintenance.candidate.__get__(self.d)
        self.d.json_command = Mock(side_effect=[
            {"digest": "sha256:" + "e" * 64, "manifests": [
                {"digest": "sha256:" + "d" * 64, "platform": {"os": "linux", "architecture": "amd64"}}]},
            {"config": {"digest": self.new_id}},
            {"config": {"Labels": {VERSION_LABEL: "2.3.5"}}}])
        candidate = self.d.candidate(self.service, self.current)
        self.assertEqual(candidate, self.target)
        for call in self.d.json_command.call_args_list[1:]:
            self.assertIn(self.new_ref, call.args[1])

    def test_readiness_requires_correct_digest_even_when_endpoint_succeeds(self):
        self.c.command = Mock(return_value={"returncode": 0, "stdout": "200"})
        self.assertEqual(self.d.readiness(self.service, self.old_id)["image_id"], self.old_id)
        with self.assertRaises(RuntimeError):
            self.d.readiness(self.service, self.new_id, timeout=0)

    def test_lifecycle_contains_container_action_only_for_prepared_updates(self):
        updates, _ = self.plan()
        self.d.plan = Mock(return_value=(updates, []))
        self.d.validate = Mock(return_value=[])
        self.d.apply = Mock(return_value=[{"name": "app", "returncode": 0, "simulated": True}])
        self.assertEqual(self.c.prepare(), 0)
        plan = json.loads(next(self.c.state.glob("*.plan.json")).read_text())
        self.assertEqual([a["id"] for a in plan["actions"]], ["apt_update", "apt_upgrade", "container_update", "verify"])
        self.assertEqual(self.c.maintain(), 0)
        self.d.apply.assert_called_once()

    def test_archive_is_read_back_without_extracting_and_kept_private(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            item = tarfile.TarInfo("database.sqlite")
            data = b"test snapshot"
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
        def copy_archive(argv, **kwargs):
            kwargs["stdout"].write(stream.getvalue())
            return Mock(returncode=0, stderr=b"")
        target = self.root / "data.tar"
        with patch("container_maintenance.subprocess.run", side_effect=copy_archive):
            result = self.d.archive("container-id", self.current["mounts"][0], target, 1024 * 1024)
        self.assertEqual(result["files"], 1)
        self.assertEqual(len(result["sha256"]), 64)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.root / "database.sqlite").exists())

    def test_post_replacement_failure_keeps_backups_without_database_downgrade(self):
        updates, _ = self.plan()
        self.c.dry_run = False
        def execute(action, argv, **kwargs):
            if action == "container_stop_for_backup":
                self.current["running"] = False
            return ""
        self.d.command = Mock(side_effect=execute)
        self.d.json_command = Mock(return_value=[{"Id": self.new_id, "Config": {"Labels": self.target["versions"]}}])
        self.d.readiness = Mock(side_effect=[self.current, RuntimeError("unhealthy new image")])
        self.d.archive = Mock(return_value={"sha256": "verified"})
        self.c.command = Mock()
        result = self.d.apply(updates, "CHG-20260913")
        self.assertEqual(result[0]["returncode"], 1)
        self.assertTrue(result[0]["replacement_started"])
        self.assertTrue((Path(result[0]["backup"]) / "previous-image.json").exists())
        self.assertFalse(self.d.override(self.service).exists())
        self.c.command.assert_not_called()

    def test_rendered_sandbox_access_is_scoped_and_repeatable(self):
        config = {"schedule": {"preparation_day": "Saturday", "maintenance_day": "Sunday", "maintenance_hour_utc": 3},
                  "paths": {"log_dir": "/var/log/example"}, "containers": self.c.config["containers"]}
        output = self.root / "rendered"
        render(config, output)
        before = (output / "ai-sysadmin-maintenance.containers.conf").read_text()
        render(config, output)
        self.assertEqual(before, (output / "ai-sysadmin-maintenance.containers.conf").read_text())
        self.assertIn("ProtectHome=tmpfs", before)
        self.assertIn("BindReadOnlyPaths=" + str(self.root), before)
