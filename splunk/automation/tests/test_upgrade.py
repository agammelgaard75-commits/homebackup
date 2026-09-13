import copy
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import upgrade as u
import cold


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((u.HERE / 'config.json').read_text())
        self.inv = dict(version='9.3.14', core_branch='9.3', standalone=True,
                        external_index_paths=[], cpu_flags=['aes', 'sse4_2'], apps=[])

    def test_health_report_names_unhealthy_feature_and_blocks(self):
        cfg = {**self.cfg, 'local_apps': {}, 'splunkbase_apps': {}, 'smoke_searches': []}
        api = Mock()
        values = {
            '/services/server/health/splunkd': {'health': 'red'},
            '/services/server/health/splunkd/details': {'features': {
                'Resource Usage': {'features': {'IOWait': {'health': 'red'}}}}},
            '/services/kvstore/status': {'current': {'status': 'ready'}},
            '/services/server/info': {'licenseState': 'OK'},
        }
        api.get.side_effect = lambda path: {'entry': [{'content': values[path]}]}
        with patch('upgrade.execute', return_value=Mock(returncode=0, stdout='', stderr='')):
            result = u.validate(api, cfg)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('Resource Usage/IOWait=red', result['errors'][0]['message'])
        self.assertFalse(next(c for c in result['checks'] if c['name'] == 'splunk_health')['passed'])

    def test_rejected_bundled_release_is_not_installable(self):
        self.inv['apps'] = [dict(name='python_upgrade_readiness_app', kind='bundled', version='4.6.2')]
        core = b'https://download.splunk.com/products/splunk/releases/9.3.14/linux/splunk-9.3.14-abc-Linux-x86_64.tgz'
        catalog = json.dumps({'results': [{'appid': 'python_upgrade_readiness_app', 'uid': 5483}], 'total': 1}).encode()
        releases = json.dumps([{'name': '4.7.0', 'install_method_single': 'rejected'}]).encode()
        with patch('upgrade.fetch', side_effect=[core, core, catalog, releases]):
            result = u.discover(self.cfg, self.inv)
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['errors'][0]['code'], 'APP_RELEASE_REJECTED')

    def test_numeric_order_and_prerelease_rejected(self):
        self.assertGreater(u.version('9.3.14'), u.version('9.3.9'))
        with self.assertRaises(ValueError):
            u.version('10.5.0-beta')

    def test_no_uf_or_wrong_arch_release(self):
        text = '''https://download.splunk.com/products/splunk/releases/9.3.15/linux/splunk-9.3.15-abc-Linux-x86_64.tgz
        https://download.splunk.com/products/universalforwarder/releases/10.4.3/linux/splunkforwarder-10.4.3-abc-linux-amd64.tgz
        https://download.splunk.com/products/splunk/releases/10.4.3/linux/splunk-10.4.3-abc-linux-arm64.tgz'''
        self.assertEqual([x['version'] for x in u.parse_core(text)], ['9.3.15'])

    def test_cpu_gate_independent_of_branch_configuration(self):
        self.cfg['allowed_core_branch'] = '10.4'
        c = dict(kind='core', name='splunk', version='10.4.3')
        self.assertIn('CORE_CPU', [e['code'] for e in u.gates(self.cfg, self.inv, c, {})])

    def test_cluster_and_external_storage_block(self):
        for key, value in [('standalone', False), ('external_index_paths', ['main:homePath'])]:
            inv = copy.deepcopy(self.inv)
            inv[key] = value
            self.assertIn('TOPOLOGY', [e['code'] for e in u.gates(self.cfg, inv, None, {})])

    def test_disabled_unknown_apps_are_not_ignored(self):
        self.inv['apps'] = [dict(name='unknown', kind='unknown', disabled=True)]
        self.assertIn('APP_UNMAPPED', [e['code'] for e in u.gates(self.cfg, self.inv, None, {})])

    def test_app_requires_exact_release_compatibility(self):
        self.inv['apps'] = [dict(name='TA_x', kind='splunkbase', version='1.0.0')]
        self.cfg['splunkbase_apps'] = {'TA_x': {'dependencies_reviewed': True, 'smoke_searches': [{}]}}
        candidate = dict(kind='app', name='TA_x', version='1.1.0', install_method_single='simple')
        metadata = {'TA_x': [{'name': '1.1.0', 'product_versions': ['10.4']}]}
        self.assertIn('APP_COMPATIBILITY', [e['code'] for e in u.gates(self.cfg, self.inv, candidate, metadata)])

    def test_core_preserves_all_app_constraints(self):
        self.inv['apps'] = [dict(name='TA_x', kind='splunkbase', version='1.0.0')]
        self.cfg['splunkbase_apps'] = {'TA_x': {'dependencies_reviewed': False}}
        candidate = dict(kind='core', name='splunk', version='9.3.15')
        self.assertIn('APP_TESTS', [e['code'] for e in u.gates(self.cfg, self.inv, candidate, {})])

    def test_report_is_two_lines_per_error_and_no_status_spam(self):
        errors = [u.error('CPU', 'first\nsecond\rthird', 'fix\nthis'), u.error('OTHER', 'x' * 1000, 'y')]
        result = u.events('run', self.cfg, 'blocked', errors, '9.3.14')
        self.assertEqual(len(result), 2)
        for event in result:
            self.assertEqual(len(event['message'].splitlines()), 2)
            self.assertLessEqual(max(map(len, event['message'].splitlines())), 240)
            self.assertEqual(len(json.dumps(event).splitlines()), 1)
        good = u.events('run', self.cfg, 'up_to_date', [], '9.3.14')
        self.assertEqual(len(good), 1)
        self.assertEqual(len(good[0]['message'].splitlines()), 1)

    def test_pending_report_kept_when_indexing_unconfirmed(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            (state / 'outbox').mkdir()
            pending = state / 'outbox/a.json'
            u.atomic_json(pending, dict(event_id='id'))
            api = Mock()
            api.request.return_value = '{"ok":true}'
            api.search.return_value = []
            with patch('upgrade.time.sleep'), self.assertRaises(RuntimeError):
                u.flush(api, self.cfg, state)
            self.assertTrue(pending.exists())
            api.search.return_value = [{'event_id': 'id'}]
            u.flush(api, self.cfg, state)
            self.assertFalse(pending.exists())

    def test_network_release_failures_are_not_no_updates(self):
        with patch('upgrade.fetch', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                u.discover(self.cfg, self.inv)

    def test_bad_checksum_rejected_before_backup(self):
        candidate = dict(kind='core', name='splunk', version='9.3.15', url='https://download.splunk.com/test.tgz')
        with tempfile.TemporaryDirectory() as temp, patch('upgrade.fetch', side_effect=[b'bad package', b'0' * 128]):
            with self.assertRaisesRegex(RuntimeError, 'SHA-512'):
                u.download(candidate, Path(temp))

    def test_tar_traversal_and_special_files_rejected(self):
        for name, kind in [('splunk/../../etc/passwd', tarfile.REGTYPE),
                           ('other/file', tarfile.REGTYPE), ('splunk/device', tarfile.CHRTYPE)]:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'x.tgz'
                with tarfile.open(path, 'w:gz') as archive:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    archive.addfile(member)
                with self.assertRaises(ValueError):
                    cold.checked_archive(path, 'splunk')

    def test_post_upgrade_failure_restores_and_latches(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            run = state / ('a' * 32)
            run.mkdir()
            inv = self.inv
            candidate = dict(kind='core', name='splunk', version='9.3.15')
            good = {'checks': [], 'errors': []}
            bad = {'checks': [], 'errors': [u.error('TEST', 'failed', 'restore')]}
            with patch('upgrade.download', return_value=(run / 'package', 'hash')), \
                 patch('upgrade.error_counts', return_value={}), \
                 patch('upgrade.adapter') as adapter, patch('upgrade.wait_ready'), \
                 patch('upgrade.inventory', return_value=inv), patch('upgrade.time.sleep'), \
                 patch('upgrade.validate', side_effect=[bad, good]), \
                 patch('upgrade.codex', side_effect=[{'action': 'failed', 'errors': []}, {'action': 'validated', 'errors': []}]):
                status, _, errors = u.perform(self.cfg, Path('config'), Mock(), run, inv, candidate, state)
            self.assertEqual([c.args[0] for c in adapter.call_args_list], ['backup', 'core', 'restore'])
            self.assertEqual(status, 'rolled_back')
            self.assertEqual(json.loads((state / 'transaction.json').read_text())['phase'], 'restored')
            self.assertTrue(errors)

    def test_failed_backup_never_installs(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            run = state / ('b' * 32)
            run.mkdir()
            with patch('upgrade.download', return_value=(run / 'package', 'hash')), \
                 patch('upgrade.error_counts', return_value={}), \
                 patch('upgrade.adapter', side_effect=RuntimeError('backup failed')) as adapter:
                with self.assertRaises(RuntimeError):
                    u.perform(self.cfg, Path('config'), Mock(), run, self.inv,
                              dict(kind='core', name='splunk', version='9.3.15'), state)
            self.assertEqual([c.args[0] for c in adapter.call_args_list], ['backup'])
            self.assertTrue((state / 'transaction.json').exists())


if __name__ == '__main__':
    unittest.main()
