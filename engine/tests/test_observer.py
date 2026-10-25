import copy
import unittest

try:
    from groupmate.observer import prepare, validate_candidate
except ImportError:
    prepare = validate_candidate = None


def context():
    return {'snapshot_id':'s','frozen_log_id':'f','participant_id':'p','input_hash':'h',
            'rubric_version':'md', 'selected_dimensions':['C2','C3'],
            'rubric':{'dimensions':[{'dimension':d,'levels':{str(n):'anchor '+str(n) for n in range(1,5)}} for d in ['C2','C3']]},
            'verified_evidence':[{'evidence_id':'e','participant_id':'p','quote':'actual words','validation':'VALID'}],
            'knowledge':[], 'events':[], 'data_complete':True, 'opportunity':{}, 'limitations':[]}


class ObserverTests(unittest.TestCase):
    def setUp(self): self.assertIsNotNone(prepare,'Observer deterministic preparation is not implemented')

    def test_missing_rubric_precedes_no_opportunity_and_preserves_six_dimensions(self):
        c=context(); del c['rubric']; c['opportunity']={'C2':'NONE','C3':'NONE'}
        p=prepare(c)
        self.assertEqual(len(p['template']['dimensions']),6)
        self.assertEqual([d['required_status'] for d in p['dimension_constraints']],['NOT_SELECTED','DATA_INCOMPLETE','DATA_INCOMPLETE','NOT_SELECTED','NOT_SELECTED','NOT_SELECTED'])
        self.assertTrue(validate_candidate(c,p['template'])['ok'])

    def test_silence_is_not_inferred_as_no_opportunity(self):
        c=context(); c['verified_evidence']=[]
        p=prepare(c)
        self.assertEqual(p['dimension_constraints'][1]['required_status'],'INSUFFICIENT_EVIDENCE')
        c['opportunity']['C2']='NONE'
        self.assertEqual(prepare(c)['dimension_constraints'][1]['required_status'],'INSUFFICIENT_OPPORTUNITY')

    def test_incomplete_data_has_priority_even_with_evidence(self):
        c=context(); c['data_complete']=False
        self.assertEqual(prepare(c)['dimension_constraints'][1]['required_status'],'DATA_INCOMPLETE')

    def test_input_has_no_goals_or_reflection_even_if_caller_mixes_them(self):
        c=context(); c.update(goal='PRIVATE_GOAL',reflection='PRIVATE_REFLECTION',teacher_only='PRIVATE_SOURCE')
        p=prepare(c)
        self.assertNotIn('PRIVATE_',str(p))

    def test_gate_rejects_missing_dimensions_wrong_reason_and_fake_evidence(self):
        c=context(); p=prepare(c); value=copy.deepcopy(p['template'])
        value['dimensions'].pop()
        self.assertFalse(validate_candidate(c,value)['ok'])
        c['rubric']=None; value=prepare(c)['template']; value['dimensions'][1]['status']='INSUFFICIENT_OPPORTUNITY'
        self.assertIn('STATUS_C2',validate_candidate(c,value)['errors'])
        c=context(); value=prepare(c)['template']; value['dimensions'][1].update(status='OBSERVED',level=3,evidence_ids=['fake'])
        self.assertIn('EVIDENCE_C2',validate_candidate(c,value)['errors'])

    def test_gate_accepts_owned_evidence_and_does_not_change_the_model_level(self):
        c=context(); value=prepare(c)['template']; value['dimensions'][1].update(status='OBSERVED',level=3,evidence_ids=['e'],explanation='Specific comparison with anchor 3, not 4.')
        result=validate_candidate(c,value)
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['assessment']['dimensions'][1]['level'],3)
        self.assertEqual(value,result['assessment'])

    def test_gate_rejects_wrong_metadata_aggregate_boolean_level_and_foreign_evidence(self):
        c=context()
        for mutation in ['metadata','aggregate','boolean','foreign']:
            with self.subTest(mutation=mutation):
                value=prepare(c)['template']
                if mutation=='metadata': value['input_hash']='old'
                if mutation=='aggregate': value['total_score']=100
                if mutation=='boolean': value['dimensions'][1].update(status='OBSERVED',level=True,evidence_ids=['e'])
                if mutation=='foreign':
                    c['verified_evidence'][0]['participant_id']='other'
                    value['dimensions'][1].update(status='OBSERVED',level=3,evidence_ids=['e'])
                self.assertFalse(validate_candidate(c,value)['ok'])

    def test_empty_anchor_text_is_missing_rubric(self):
        c=context(); c['rubric']['dimensions'][0]['levels']['3']=''
        self.assertEqual(prepare(c)['dimension_constraints'][1]['required_status'],'DATA_INCOMPLETE')

    def test_confirmed_opportunity_cannot_be_reclassified_as_absent(self):
        c=context();c['opportunity']['C2']='PRESENT'
        value=prepare(c)['template'];value['dimensions'][1]['status']='INSUFFICIENT_OPPORTUNITY'
        self.assertIn('STATUS_C2',validate_candidate(c,value)['errors'])
