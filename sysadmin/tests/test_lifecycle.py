import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_sysadmin import Controller


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        config = root / "config.toml"
        self.config_path = config
        config.write_text(f'[paths]\nstate_dir="{root}/state"\nlog_dir="{root}/log"\n'
                          f'ignore_file="{root}/IGNORE.md"\n'
                          '[policy]\nminimum_free_root_percent=15\nmaximum_failed_units=0\n'
                          'allow_service_restart=true\npackage_update_timeout_seconds=10\n'
                          '[ai]\nrequired=false\n')
        self.c = Controller(config, dry_run=True)
        self.healthy = dict(hostname="test", root_free_percent=80, failed_units=[],
                            inspection_errors=[], reboot_required=False)
        self.c.inspect = Mock(side_effect=lambda: copy.deepcopy(self.healthy))
        self.c.approved_upgrade = Mock(return_value=(["apt-get", "-y", "--no-remove", "--only-upgrade", "install", "example=1.1"], [], []))

    def record(self):
        return next(self.c.changes.glob('*.txt'))

    def test_dry_run_preserves_live_change_and_logs(self):
        live = Controller(self.config_path)
        live.inspect = Mock(return_value=self.healthy.copy())
        live.command = Mock(return_value={'returncode': 0})
        live.approved_upgrade = self.c.approved_upgrade
        live.prepare()
        live_files = [p for directory in (live.state, live.logs)
                      for p in directory.rglob('*') if p.is_file()]
        before = {p: p.read_bytes() for p in live_files}
        self.c.prepare()
        self.assertEqual(self.c.maintain(), 0)
        self.assertEqual(before, {p: p.read_bytes() for p in live_files})
        self.assertNotEqual(live.state, self.c.state)
        self.assertNotEqual(live.logs, self.c.logs)
        self.assertEqual(live.maintain(), 0)
        self.assertEqual(live.command.call_count, 2)

    def test_dry_run_cannot_supply_live_change(self):
        self.c.prepare()
        self.c.maintain()
        live = Controller(self.config_path)
        live.command = Mock()
        self.assertEqual(live.maintain(), 3)
        live.command.assert_not_called()

    def test_package_failures_emit_anomaly(self):
        self.c.prepare()
        self.c.command = Mock(side_effect=[{'returncode': 0}, {'returncode': 100, 'stderr': 'package failed'}])
        self.assertEqual(self.c.maintain(), 1)
        events = [json.loads(line) for line in (self.c.logs/'anomalies.jsonl').read_text().splitlines()]
        failure = next(event for event in events if event.get('action') == 'apt_upgrade')
        self.assertEqual(failure['returncode'], 100)
        self.assertEqual(failure['severity'], 'high')
        self.assertEqual(failure['change_id'], self.record().stem)
        self.assertEqual(failure['run_id'], self.c.run_id)

    def test_update_failure_stops_upgrade_and_emits_anomaly(self):
        self.c.prepare()
        self.c.command = Mock(return_value={'returncode': 124})
        self.assertEqual(self.c.maintain(), 1)
        self.assertEqual(self.c.command.call_count, 1)
        events = [json.loads(line) for line in (self.c.logs/'anomalies.jsonl').read_text().splitlines()]
        self.assertTrue(any(e.get('action') == 'apt_update' and e['returncode'] == 124 for e in events))

    def test_status_mentions_in_notes_do_not_control_execution(self):
        self.c.prepare()
        notes = '\nOperator note: earlier change had Status: CLOSED\nStatus: FAILED\nStatus: RUNNING\n'
        self.record().write_text(self.record().read_text() + notes)
        self.c.command = Mock(return_value={'returncode': 0})
        self.assertEqual(self.c.maintain(), 0)
        self.assertEqual(self.c.command.call_count, 2)
        header = self.record().read_text().split('\n\n', 1)[0]
        self.assertIn('\nStatus: CLOSED\n', header)
        self.assertTrue(self.record().read_text().endswith(notes))

    def test_invalid_header_status_refuses_execution(self):
        self.c.prepare()
        original = self.record().read_text()
        for status in ('Status: UNKNOWN', 'Status: PREPARED\nStatus: CLOSED', 'Missing status'):
            with self.subTest(status=status):
                changed = original.replace('Status: PREPARED', status, 1)
                self.record().write_text(changed)
                self.c.command = Mock()
                self.assertEqual(self.c.maintain(), 1)
                self.c.command.assert_not_called()
                self.assertEqual(self.record().read_text(), changed)

    def test_closed_change_preserved(self):
        self.c.prepare()
        self.assertEqual(self.c.maintain(), 0)
        before = self.record().read_bytes()
        self.c.prepare()
        self.c.maintain()
        self.assertEqual(before, self.record().read_bytes())

    def test_prepared_plan_preserved(self):
        self.c.prepare()
        plan = next(self.c.state.glob('*.plan.json'))
        before = plan.read_bytes(), self.record().read_bytes()
        self.healthy['root_free_percent'] = 1
        self.c.prepare()
        self.assertEqual(before, (plan.read_bytes(), self.record().read_bytes()))

    def test_failed_run_not_automatically_retried(self):
        self.c.prepare()
        self.c.command = Mock(return_value={'returncode': 1})
        self.assertEqual(self.c.maintain(), 1)
        before = self.record().read_bytes()
        self.c.command.reset_mock()
        self.assertEqual(self.c.maintain(), 1)
        self.c.command.assert_not_called()
        self.assertEqual(before, self.record().read_bytes())

    def test_preflight_blocks_commands(self):
        self.c.prepare()
        self.healthy['root_free_percent'] = 1
        self.c.command = Mock()
        self.assertEqual(self.c.maintain(), 2)
        self.c.command.assert_not_called()

    def test_unhealthy_postflight_fails(self):
        self.c.prepare()
        self.c.inspect = Mock(side_effect=[self.healthy, dict(self.healthy, failed_units=['ssh.service'])])
        self.assertEqual(self.c.maintain(), 1)
        self.assertIn('Status: FAILED', self.record().read_text())

    def test_timeout_bytes_logged(self):
        with patch('ai_sysadmin.subprocess.run', side_effect=subprocess.TimeoutExpired(['test'], 1, output=b'partial')):
            result = self.c.command('test', ['test'])
        self.assertEqual(result['returncode'], 124)
        self.assertEqual(result['stdout'], 'partial')

    def test_missing_command_logged(self):
        with patch('ai_sysadmin.subprocess.run', side_effect=FileNotFoundError()):
            self.assertEqual(self.c.command('test', ['test'])['returncode'], 127)

    def test_tampered_plan_rejected(self):
        self.c.prepare()
        plan = next(self.c.state.glob('*.plan.json'))
        data = json.loads(plan.read_text())
        data['actions'] = []
        plan.write_text(json.dumps(data))
        self.c.command = Mock()
        self.assertEqual(self.c.maintain(), 1)
        self.c.command.assert_not_called()

    def test_exception_closes_change(self):
        self.c.prepare()
        self.c.inspect = Mock(side_effect=RuntimeError())
        self.assertEqual(self.c.maintain(), 1)
        self.assertIn('Status: FAILED', self.record().read_text())

    def test_failed_orphan_retry_preserves_history_and_is_repeatable(self):
        self.c.prepare()
        source = self.record()
        self.c.close(source, source.read_text(), source.stem, "FAILED", "Reviewed failure")
        (self.c.state / "current-change").unlink()
        (self.c.state / f"{source.stem}.plan.json").unlink()
        original = source.read_bytes()
        self.assertEqual(self.c.prepare(), 1)
        self.assertFalse((self.c.state / "current-change").exists())
        self.assertEqual(self.c.prepare(source.stem, "Health issue remediated"), 0)
        retry = source.stem + "-R1"
        self.assertEqual((self.c.state / "current-change").read_text().strip(), retry)
        snapshot = {p: p.read_bytes() for p in self.c.state.rglob('*') if p.is_file()}
        self.assertEqual(self.c.prepare(source.stem, "Health issue remediated"), 0)
        self.assertEqual(self.c.prepare(), 0)
        self.assertEqual(snapshot, {p: p.read_bytes() for p in snapshot})
        self.c.command = Mock(return_value={"returncode": 0})
        self.assertEqual(self.c.maintain(), 0)
        self.assertEqual(self.c.maintain(), 0)
        self.assertEqual(self.c.command.call_count, 2)
        self.assertEqual(self.c.prepare(source.stem, "Health issue remediated"), 0)
        self.assertEqual(len(list(self.c.changes.glob('*.txt'))), 2)
        self.assertEqual(source.read_bytes(), original)

    def test_retry_requires_failed_source_and_reason(self):
        self.c.prepare()
        source = self.record()
        self.assertEqual(self.c.prepare(source.stem, "Reviewed"), 3)
        self.assertEqual(self.c.prepare("../../etc/passwd", "Reviewed"), 3)
        self.assertEqual(self.c.prepare(source.stem, " "), 3)
        self.assertEqual(len(list(self.c.changes.glob('*.txt'))), 1)

    def test_prepared_pointer_repaired_without_replanning(self):
        self.c.prepare()
        pointer = self.c.state / "current-change"
        pointer.unlink()
        self.c.inspect.reset_mock()
        self.assertEqual(self.c.prepare(), 0)
        self.assertEqual(pointer.read_text().strip(), self.record().stem)
        self.c.inspect.assert_not_called()

    def test_empty_pointer_creates_first_preparation(self):
        pointer = self.c.state / "current-change"
        pointer.touch()
        self.assertEqual(self.c.prepare(), 0)
        self.assertEqual(pointer.read_text().strip(), self.record().stem)
        self.c.inspect.assert_called_once()

    def test_blank_prepared_pointer_repaired_without_replanning(self):
        self.c.prepare()
        pointer = self.c.state / "current-change"
        artifacts = {p: p.read_bytes() for p in self.c.state.rglob('*')
                     if p.is_file() and p != pointer}
        self.c.inspect.reset_mock()
        for blank in ("", " \n\t"):
            with self.subTest(blank=blank):
                pointer.write_text(blank)
                self.assertEqual(self.c.prepare(), 0)
                self.assertEqual(pointer.read_text().strip(), self.record().stem)
                self.assertEqual(self.c.prepare(), 0)
                self.assertEqual(artifacts, {p: p.read_bytes() for p in artifacts})
        self.c.inspect.assert_not_called()

    def test_closed_pointer_restored_without_repeating_maintenance(self):
        self.c.prepare()
        self.assertEqual(self.c.maintain(), 0)
        pointer = self.c.state / "current-change"
        before = self.record().read_bytes()
        self.c.inspect.reset_mock()
        self.c.command = Mock()
        for blank in (None, ""):
            with self.subTest(blank=blank):
                if blank is None:
                    pointer.unlink()
                else:
                    pointer.write_text(blank)
                self.assertEqual(self.c.prepare(), 0)
                self.assertEqual(pointer.read_text().strip(), self.record().stem)
                self.assertEqual(self.c.maintain(), 0)
                self.assertEqual(self.record().read_bytes(), before)
        self.c.inspect.assert_not_called()
        self.c.command.assert_not_called()

    def test_malformed_nonempty_pointer_still_rejected(self):
        pointer = self.c.state / "current-change"
        pointer.write_text("../../etc/passwd")
        self.assertEqual(self.c.prepare(), 3)
        self.assertEqual(pointer.read_text(), "../../etc/passwd")
        self.c.inspect.assert_not_called()

    def test_lost_pointer_cannot_hide_older_running_or_invalid_record(self):
        self.c.prepare()
        record = self.record()
        original = record.read_text()
        record.rename(self.c.changes / "CHG-20000101.txt")
        older = self.c.changes / "CHG-20000101.txt"
        pointer = self.c.state / "current-change"
        self.c.inspect.reset_mock()
        for status, expected in (("RUNNING", 1), ("UNKNOWN", 3)):
            older.write_text(original.replace("Status: PREPARED", "Status: " + status))
            for blank in (None, ""):
                with self.subTest(status=status, blank=blank):
                    if blank is None:
                        pointer.unlink(missing_ok=True)
                    else:
                        pointer.write_text(blank)
                    self.assertEqual(self.c.prepare(), expected)
                    self.assertEqual(len(list(self.c.changes.glob('*.txt'))), 1)
                    self.assertEqual(pointer.read_text() if pointer.exists() else None, blank)
        self.c.inspect.assert_not_called()

    def test_empty_pointer_does_not_bypass_failed_change_or_invalid_plan(self):
        self.c.prepare()
        pointer = self.c.state / "current-change"
        pointer.write_text("")
        next(self.c.state.glob('*.plan.json')).unlink()
        self.assertEqual(self.c.prepare(), 3)
        self.assertEqual(pointer.read_text(), "")
        record = self.record()
        record.write_text(record.read_text().replace("Status: PREPARED", "Status: FAILED"))
        self.assertEqual(self.c.prepare(), 1)
        self.assertEqual(pointer.read_text(), "")

    def test_missing_prepared_plan_never_reports_success(self):
        self.c.prepare()
        next(self.c.state.glob('*.plan.json')).unlink()
        pointer = self.c.state / "current-change"
        pointer.unlink()
        original = self.record().read_bytes()
        self.assertEqual(self.c.prepare(), 3)
        self.assertFalse(pointer.exists())
        self.assertEqual(original, self.record().read_bytes())

    def test_blocked_preparation_stays_blocked_on_repeat(self):
        self.healthy['root_free_percent'] = 1
        self.assertEqual(self.c.prepare(), 2)
        self.assertEqual(self.c.prepare(), 2)

    def test_running_change_cannot_be_superseded(self):
        self.c.prepare()
        source = self.record()
        source.write_text(source.read_text().replace('Status: PREPARED', 'Status: RUNNING'))
        before = source.read_bytes()
        self.assertEqual(self.c.prepare(), 1)
        self.assertEqual(self.c.prepare(source.stem, "Reviewed"), 3)
        self.assertEqual(source.read_bytes(), before)

    def test_automatic_restart_loop_is_reported_and_blocks_maintenance(self):
        loop = 'Splunkd.service loaded activating auto-restart Splunk daemon'
        self.c.command = Mock(side_effect=[{'returncode': 0, 'stdout': loop},
                                           {'returncode': 0, 'stdout': ''}])
        self.c.software_inventory = Mock(return_value={"apt_packages": {}, "extra": [], "errors": [], "package_version_conflicts": []})
        inspection = Controller.inspect(self.c)
        self.assertEqual(inspection['failed_units'], [loop])
        self.assertIn('--state=failed,auto-restart', self.c.command.call_args_list[0].args[1])
        self.assertIn('Failed systemd units exceed policy', self.c.blockers(inspection))
        events = [json.loads(line) for line in (self.c.logs/'anomalies.jsonl').read_text().splitlines()]
        self.assertTrue(any(e.get('failed_units') == [loop] for e in events))

    def test_restart_policy_blocks(self):
        self.c.config['policy']['allow_service_restart'] = False
        self.assertTrue(self.c.blockers(self.healthy))

    def test_missing_ai_blocks(self):
        self.c.config['ai']['required'] = True
        self.assertTrue(self.c.plan(self.healthy)['blocked_reasons'])

    def test_ai_cannot_override_safety(self):
        self.c.config['ai'] = {'required': True, 'command': ['/trusted/adapter']}
        self.healthy['root_free_percent'] = 1
        with patch('ai_sysadmin.subprocess.run', return_value=Mock(stdout='{"proceed":true,"reasoning":"ok"}')):
            self.assertTrue(self.c.plan(self.healthy)['blocked_reasons'])

    def test_malformed_ai_blocks(self):
        self.c.config['ai'] = {'required': True, 'command': ['/trusted/adapter']}
        with patch('ai_sysadmin.subprocess.run', return_value=Mock(stdout='[]')):
            self.assertTrue(self.c.plan(self.healthy)['blocked_reasons'])

    def test_stale_plan_rejected(self):
        self.c.prepare()
        path = next(self.c.state.glob('*.plan.json'))
        plan = json.loads(path.read_text())
        plan.pop('sha256')
        plan['generated_at'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat()
        plan['sha256'] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        path.write_text(json.dumps(plan))
        self.c.command = Mock()
        self.assertEqual(self.c.maintain(), 1)
        self.c.command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
