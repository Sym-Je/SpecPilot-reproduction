import math
import json
from pathlib import Path
import tempfile
import unittest


class ConfirmationTests(unittest.TestCase):
    def test_selection_excludes_previous_identity_and_near_duplicates(self):
        from exp.confirmation import choose
        pool = [dict(suite='chinese-qa', source_id=str(index), prompt=chr(0x5000+index)*45,
                     input_ids=list(range(index+1))) for index in range(100)]
        first = choose(pool, [pool[0]['prompt']], {'1'}, 20)
        second = choose(list(reversed(pool)), [pool[0]['prompt']], {'1'}, 20)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 20)
        self.assertEqual(sum(row['input_band']=='short' for row in first), 10)
        self.assertFalse({'0','1'} & {row['source_id'] for row in first})

    def test_selection_refuses_insufficient_unique_items(self):
        from exp.confirmation import choose
        with self.assertRaises(ValueError):
            choose([], [], set(), 60)

    def test_conditions_are_disjoint_and_do_not_force_eos(self):
        from exp.confirmation import condition_requests
        requests = [dict(id='qa',suite='chinese-qa'),dict(id='sum',suite='summary'),dict(id='code',suite='humaneval')]
        self.assertEqual([row['id'] for row in condition_requests(requests,2048)], ['qa','sum'])
        self.assertEqual([row['id'] for row in condition_requests(requests,4096)], ['code'])
        with self.assertRaises(ValueError): condition_requests(requests,256)

    def test_confirmation_intervals_control_three_primary_tests(self):
        from exp.confirmation import interval
        values=[-.3,-.2,-.1,.05,.1,.2]
        ordinary=interval(values)
        simultaneous=interval(values,simultaneous=True)
        self.assertLessEqual(simultaneous['lower'],ordinary['lower'])
        self.assertGreaterEqual(simultaneous['upper'],ordinary['upper'])
        self.assertEqual(simultaneous['family_size'],3)

    def test_interval_rejects_empty_nan_and_singleton(self):
        from exp.confirmation import interval
        for values in ([],[0.1],[math.nan,1.]):
            with self.assertRaises(ValueError): interval(values)

    def test_outcome_does_not_treat_overlap_as_noninferiority(self):
        from exp.confirmation import outcome
        self.assertEqual(outcome(dict(lower=.8,upper=.95),1),'confirmed-counterexample')
        self.assertEqual(outcome(dict(lower=.8,upper=1.1),1),'insufficient-evidence')
        self.assertEqual(outcome(dict(lower=1.1,upper=1.2),1),'opposite-direction-on-this-sample')

    def test_conditions_reject_unknown_domain(self):
        from exp.confirmation import condition_requests
        with self.assertRaises(ValueError): condition_requests([dict(id='bad',suite='unknown')],2048)

    def test_dialogsum_test_schema_uses_first_fixed_human_reference(self):
        from exp.confirmation import summary_rows
        rows=summary_rows([dict(fname='synthetic-id',dialogue='A: hello',summary1='Greeting.',
                                summary2='An alternative reference.',summary3='Third.')])
        self.assertEqual(rows[0]['answer'],'Greeting.')
        self.assertEqual(rows[0]['reference_kind'],'human-authored-summary1')
        with self.assertRaises(ValueError): summary_rows([dict(fname='bad',dialogue='A: hello')])

    def test_quality_is_clustered_bound_and_refuses_missing_or_duplicate_rows(self):
        from exp.confirmation import quality_metrics
        requests=[dict(id='first',suite='summary'),dict(id='second',suite='summary')]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            rows=[]
            for number in (1,2):
                directory=root/'candidate'/f'round-{number:02d}'
                directory.mkdir(parents=True)
                pairs=[]
                for request in requests:
                    pair=dict(id=request['id'])
                    for key,role,score in (('a','stock',.5),('b','final',.3)):
                        digest=role+request['id']
                        pair[key]=dict(output_sha256=digest)
                        rows.append(dict(round=number,role=role,id=request['id'],suite='summary',
                            output_sha256=digest,quality=dict(score=score,metric='rouge_l')))
                    pairs.append(pair)
                (directory/'pairs.jsonl').write_text(''.join(json.dumps(pair)+'\n' for pair in pairs))
            def save(values):
                (root/'quality.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in values))
            save(rows)
            result=quality_metrics(root,requests)['summary']
            self.assertEqual(result['n'],2)
            self.assertEqual(result['outcome'],'confirmed-counterexample')
            self.assertFalse(result['semantic_noninferiority_proven'])
            for bad in (rows[:-1],rows+rows[:1]):
                save(bad)
                with self.assertRaises(ValueError): quality_metrics(root,requests)
            rows[0]['output_sha256']='tampered'
            save(rows)
            with self.assertRaises(ValueError): quality_metrics(root,requests)


if __name__=='__main__':
    unittest.main()
