import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from litellm_planner import assess


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.ai = {'base_url': 'http://127.0.0.1:4000/v1', 'model': 'test-model',
                   'timeout_seconds': 60, 'api_key_file': '/absent/test-key'}

    def test_authenticated_chat_request(self):
        response = {'choices': [{'message': {'content': '{"proceed":true,"reasoning":"Healthy"}'}}]}
        with patch.dict(os.environ, {'LITELLM_API_KEY': 'test-key'}), patch(
                'litellm_planner.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as call:
            result = assess(self.ai, {'inspection': 'test'})
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, 'http://127.0.0.1:4000/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
        payload = json.loads(request.data)
        self.assertEqual(payload['model'], 'test-model')
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertNotIn('test-key', request.data.decode())
        self.assertEqual(result, {'proceed': True, 'reasoning': 'Healthy'})

    def test_file_credential_and_rejected_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp)/'key'
            key.write_text('file-test-key\n')
            self.ai['api_key_file'] = str(key)
            response = {'choices': [{'message': {'content': '{"proceed":"yes"}'}}]}
            with patch.dict(os.environ, {}, clear=True), patch(
                    'litellm_planner.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as call:
                with self.assertRaises(ValueError):
                    assess(self.ai, {})
                self.assertEqual(call.call_args.args[0].get_header('Authorization'), 'Bearer file-test-key')

    def test_missing_credential_makes_no_request(self):
        with patch.dict(os.environ, {}, clear=True), patch('litellm_planner.urllib.request.urlopen') as call:
            with self.assertRaises(FileNotFoundError):
                assess(self.ai, {})
            call.assert_not_called()
