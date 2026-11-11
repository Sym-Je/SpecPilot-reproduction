import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from harness.headroom_evidence import compact_graph,matching_timing,verify_attachment


class HeadroomEvidenceTests(unittest.TestCase):
    def test_compact_graph_preserves_counts_and_never_claims_exposure_or_instance_fqn(self):
        group=dict(kernel='gemm',operation='aten::mm',tensors=[],count=2,work_us=3,first_event_index=7)
        trace=dict(kernel_count=3,kernel_work_us=4,mapped_kernel_count=2,unmatched_kernel_count=1,
            groups=[group],source={'sha256':'a'*64})
        graph=dict(traces=[trace,copy.deepcopy(trace)],capture_records=2,captured_nodes=3,graph_mapping_assumption='recorded IDs')
        result=compact_graph(graph)
        self.assertEqual(result['matched_count'],4)
        self.assertEqual(result['top_groups'][0]['count'],4)
        self.assertFalse(result['module_instance_fqn_known'])
        self.assertIsNone(result['exposed_time_us'])

    def test_matched_request_and_output_cannot_hide_different_workload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);timing=root/'timing';mapping=root/'mapping';(mapping/'stock').mkdir(parents=True)
            row=dict(input_sha256='a'*64,output_ids=[1,2],tokens=2,latency_ms=4)
            pair=dict(id='public-id',a=row,b=copy.deepcopy(row))
            sample=dict(id='public-id',row=copy.deepcopy(row))
            (mapping/'stock/samples.json').write_text(json.dumps([sample]))
            for number in (1,2):
                directory=timing/f'round-{number:02d}';directory.mkdir(parents=True)
                (directory/'pairs.jsonl').write_text(json.dumps(pair)+'\n')
            clocks=[dict(id='public-id',round=number,decode_step_ns=2e6,request_elapsed_ns=10e6,
                decode_steps=4,decode_elapsed_ns=8e6) for number in (1,2)]
            origins=dict(timing=('timing','unused'),mapping=('mapping','unused'))
            with patch('harness.headroom_evidence.ORIGINS',origins):
                result=matching_timing(root,dict(result=dict(clocks=clocks)))
                self.assertTrue(result['same_request_and_output_verified'])
                self.assertEqual(result['mean_decode_step_ms'],2)
                clocks[0]['id']='different-request'
                with self.assertRaises(ValueError):matching_timing(root,dict(result=dict(clocks=clocks)))
                clocks[0]['id']='public-id'
                sample['row']['output_ids']=[1,3]
                (mapping/'stock/samples.json').write_text(json.dumps([sample]))
                with self.assertRaises(ValueError):matching_timing(root,dict(result=dict(clocks=clocks)))

    def test_attachment_requires_unmodified_packet_and_input_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'packet.json';path.write_text('{}')
            evidence=dict(headroom=dict(packet=dict(path=str(path),sha256='0'*64),inputs={}))
            with self.assertRaises(ValueError):verify_attachment(root,evidence)


if __name__=='__main__':unittest.main()
