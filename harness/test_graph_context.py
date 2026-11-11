import copy
import unittest

from harness.graph_context import checked_exec,node_index,summarize,tensor_shapes


def capture():
    return dict(schema='graph-provenance-v1',pid=3,tree_sha='a'*64,instrumentation='read-only',
        unassigned_nodes=[],operations=[dict(name='aten::mm',
        inputs=[dict(shape=[8,16],dtype='torch.bfloat16',device='cuda:0'), 'PRIVATE_TENSOR_CONTENT'],
        outputs=dict(shape=[8,32],dtype='torch.bfloat16',device='cuda:0'),
        nodes=[dict(device=0,graph_id=4,node_id=(4<<32)|7,node_type=0)])])


class GraphContextTests(unittest.TestCase):
    def test_recorded_exec_remap_keeps_descriptors_exact_and_detects_shape_forgery(self):
        original=capture();record=copy.deepcopy(original);record['exec_id']=5
        record['operations'][0]['nodes'][0].update(graph_id=5,node_id=(5<<32)|7)
        checked_exec(record,original)
        record['operations'][0]['outputs']['shape']=[1,32]
        with self.assertRaises(ValueError):checked_exec(record,original)

    def test_mapping_is_by_full_identity_not_name_or_temporal_proximity(self):
        nodes=node_index([capture()])
        event=dict(cat='kernel',ph='X',name='gemm',dur=2,args={'device':0,'graph id':4,'graph node id':(4<<32)|7})
        other=copy.deepcopy(event);other['args']['graph id']=5
        result=summarize([event,other],nodes)
        self.assertEqual(result['mapped_kernel_count'],1)
        self.assertEqual(result['unmatched_kernel_count'],1)
        self.assertIsNone(result['exposed_time_us'])
        self.assertNotIn('PRIVATE_TENSOR_CONTENT',str(result))

    def test_duplicate_ids_and_unapproved_tensor_descriptors_reject(self):
        with self.assertRaises(ValueError):node_index([capture(),capture()])
        with self.assertRaises(ValueError):tensor_shapes(dict(shape=[1],dtype='SECRET',device='cuda:0'))

    def test_torch_linear_module_metadata_is_supported_without_importing_torch(self):
        record=capture();record['operations'][0]['name']='module:torch.nn.modules.linear.Linear'
        self.assertEqual(len(node_index([record])),1)


if __name__=='__main__':unittest.main()
