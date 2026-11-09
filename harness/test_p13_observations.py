import copy
import unittest


class ObservationTests(unittest.TestCase):
    def observations(self):
        requests=[]
        for index,sequence in enumerate(([0,0,0,1],[7,7,6,7],[4,3,4,3])):
            requests.append(dict(request_group=f'probe-{index+1}',suite='first' if index==0 else 'second',
                rounds=[dict(round=number,accepted_counts=list(sequence),uncommitted_emitted_before_finish=[True]) for number in (1,2)]))
        return dict(schema='count-order-observations-v1',requests=requests)

    def test_physical_repeats_are_not_independent_training_rows(self):
        from harness.exploration_observations import history_screen
        result=history_screen(self.observations())
        self.assertEqual(result['independent_requests'],3)
        self.assertEqual(len(result['per_request']),3)
        self.assertTrue(result['per_request'][0]['suite_fallback_to_global'])
        self.assertIsNone(result['end_to_end_gain'])
        self.assertFalse(result['population_generalization_established'])

    def test_held_out_values_do_not_fit_their_own_constant_baseline(self):
        from harness.exploration_observations import history_screen
        values=self.observations()
        before=history_screen(values)['per_request'][0]['training_constants']
        for row in values['requests'][0]['rounds']:
            row['accepted_counts']=[7,6,7,6]
        self.assertEqual(before,history_screen(values)['per_request'][0]['training_constants'])

    def test_repeat_drift_bad_counts_and_missing_round_are_rejected(self):
        from harness.exploration_observations import history_screen
        for mutate in (lambda values:values['requests'][0]['rounds'].pop(),
                lambda values:values['requests'][0]['rounds'][0]['accepted_counts'].__setitem__(0,2),
                lambda values:values['requests'][0]['rounds'][0]['accepted_counts'].__setitem__(0,True)):
            values=self.observations()
            mutate(values)
            with self.assertRaises(ValueError):
                history_screen(values)

    def test_event_order_never_becomes_unprofiled_latency_saving(self):
        from harness.exploration_observations import terminal_order_screen
        result=terminal_order_screen(self.observations())
        self.assertEqual(len(result['samples']),6)
        self.assertTrue(all(row['uncommitted_emitted_before_finish']==1 for row in result['samples']))
        self.assertFalse(result['native_critical_path_available'])
        self.assertFalse(result['queue_entry_timestamps_available'])
        self.assertIsNone(result['end_to_end_gain'])


if __name__=='__main__':
    unittest.main()
