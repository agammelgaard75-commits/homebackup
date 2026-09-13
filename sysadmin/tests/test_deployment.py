from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from render_deployment import render


class DeploymentTests(unittest.TestCase):
    def test_configured_schedule_and_repeatable_assets(self):
        config = {'schedule': {'maintenance_day': 'Wednesday', 'preparation_day': 'Tuesday',
                               'maintenance_hour_utc': 7}, 'paths': {'log_dir': '/var/log/ai-sysadmin'}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            render(config, root)
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            render(config, root)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertIn('OnCalendar=Wed *-*-* 07:00:00 UTC', (root/'ai-sysadmin-maintenance.timer').read_text())
            views = list(root.rglob('*.xml'))
            self.assertEqual(len(views), 3)
            for view in views:
                ET.parse(view)
            self.assertEqual((root/'ai_sysadmin/default/inputs.conf').read_text().count('[monitor:'), 3)
            self.assertIn('maxTotalDataSizeMB = 2048', (root/'ai_sysadmin/default/indexes.conf').read_text())
            self.assertTrue((root/'ai_sysadmin/metadata/default.meta').exists())
            dashboard = (root/'ai_sysadmin/default/data/ui/views/health_dashboard.xml').read_text()
            self.assertIn("coalesce(mvcount('failed_units{}'),0)", dashboard)
            self.assertNotIn('index=os', dashboard)


    def test_invalid_schedule_rejected(self):
        config = {'schedule': {'maintenance_day': 'Wednesday', 'preparation_day': 'Monday',
                               'maintenance_hour_utc': 7}}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                render(config, Path(tmp))
