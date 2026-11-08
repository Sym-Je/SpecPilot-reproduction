from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json


class ProfileTransportTests(unittest.TestCase):
    def test_plain_text_success_is_preserved_not_rejected_as_json(self):
        from exp.diagnosis_profile import ProfileClient
        class Response:
            status=200
            headers={'Content-Type':'text/plain'}
            def read(self): return b'Start profiling.'
            def __enter__(self): return self
            def __exit__(self,*arguments): pass
        with tempfile.TemporaryDirectory() as temporary:
            client=ProfileClient('http://fixture',Path(temporary))
            with patch('exp.diagnosis_profile.urllib.request.urlopen',return_value=Response()):
                result=client.post('/start_profile',dict(output_dir='/tmp/trace'))
            self.assertEqual(result,dict(text='Start profiling.'))
            saved=json.loads((Path(temporary)/'000001.json').read_text())
            self.assertEqual(saved['http_status'],200)
            self.assertEqual(saved['response'],dict(text='Start profiling.'))
            self.assertEqual(saved['content_type'],'text/plain')

    def test_detailed_annotations_only_enabled_when_declared_by_public_schema(self):
        from exp.diagnosis_profile import annotated_body
        body=dict(output_dir='/tmp/trace')
        schema=dict(components=dict(schemas=dict(ProfileReq=dict(properties=dict(detailed_annotations={})))) )
        self.assertTrue(annotated_body(body,schema)['detailed_annotations'])
        self.assertNotIn('detailed_annotations',body)
        self.assertEqual(annotated_body(body,{}),body)

    def test_eos_audit_does_not_confuse_first_eos_with_later_continuation(self):
        from exp.diagnosis_profile import eos_summary
        self.assertEqual(eos_summary([1,9,9,9],{9}),dict(tokens=4,first_eos_index=1,post_eos_tokens=2))
        self.assertEqual(eos_summary([1,2,3],{9}),dict(tokens=3,first_eos_index=None,post_eos_tokens=0))


if __name__=='__main__': unittest.main()
