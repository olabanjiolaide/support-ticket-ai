import copy
import json
import unittest
from support_ticket_ai.proposal_metrics import compare, summarize
from support_ticket_ai.proposals import align_plan
from support_ticket_ai.resources import data_path


class ProposalMetricTests(unittest.TestCase):
    def setUp(self):
        case = json.loads(data_path('needs_proposals_development.json').read_text())['cases'][0]
        self.plan = align_plan(case['text'], case['expected_plan'])

    def test_identical_plan_and_renamed_reordered_need_ids(self):
        actual = copy.deepcopy(self.plan)
        for group in actual['groups']:
            group['id'] = {'need-1':'need-7','need-2':'need-8'}[group['id']]
        actual['groups'].reverse()
        for part in actual['parts']:
            part['group_id'] = {'need-1':'need-7','need-2':'need-8'}[part['group_id']]
        for relation in actual['relations']:
            relation['source'], relation['target'] = 'need-8', 'need-7'
        result = compare(self.plan, actual)
        self.assertEqual(result['matched_needs'], 2)
        self.assertEqual(result['correct_relation_edges'], 1)
        self.assertEqual(result['matched_relation_evidence_errors'], 0)
        self.assertEqual(result['matched_category_errors'], 0)

    def test_same_category_set_and_count_can_hide_swapped_meanings(self):
        actual = copy.deepcopy(self.plan)
        actual['groups'][0]['category'], actual['groups'][1]['category'] = 'ACCOUNT', 'ORDER'
        actual['groups'][1]['kind'] = 'goal'
        result = compare(self.plan, actual)
        self.assertTrue(result['category_set_match'])
        self.assertTrue(result['need_count_match'])
        self.assertEqual(result['matched_category_errors'], 2)
        self.assertEqual(result['matched_kind_errors'], 1)

    def test_missing_need_and_spurious_reassigned_need(self):
        actual = copy.deepcopy(self.plan)
        actual['parts'][1]['role'] = 'context'
        actual['parts'][1]['group_id'] = None
        actual['groups'].pop()
        actual['relations'] = []
        result = compare(self.plan, actual)
        self.assertEqual(result['missed_needs'], 1)
        self.assertEqual(result['missing_relation_edges'], 1)
        reverse = compare(actual, self.plan)
        self.assertEqual(reverse['extra_needs'], 1)

    def test_relationship_direction_error_is_not_hidden_by_kind_set(self):
        actual = copy.deepcopy(self.plan)
        actual['relations'][0]['source'], actual['relations'][0]['target'] = 'need-1', 'need-2'
        result = compare(self.plan, actual)
        self.assertTrue(result['relation_kind_set_match'])
        self.assertEqual(result['correct_relation_edges'], 0)
        self.assertEqual(result['missing_relation_edges'], 1)
        self.assertEqual(result['extra_relation_edges'], 1)

    def test_excluded_text_misread_as_active_is_counted(self):
        expected = copy.deepcopy(self.plan)
        expected['parts'][0]['role'] = 'negated'
        result = compare(expected, self.plan)
        self.assertGreater(result['negated_or_resolved_as_active_characters'], 0)
        with self.assertRaises(ValueError):
            compare(expected, {**self.plan, 'source_text':'different'})

    def test_failures_not_silently_dropped_from_summary(self):
        rows = [{'valid_structured_response':True,'metrics':compare(self.plan,self.plan),'elapsed_seconds':2},
                {'valid_structured_response':False,'metrics':None,'elapsed_seconds':8}]
        result = summarize(rows)
        self.assertEqual(result['structural_success_rate'], 0.5)
        self.assertEqual(result['failed_responses'], 1)
        self.assertEqual(result['p95_elapsed_seconds_all_attempts'], 8)
        self.assertEqual(summarize([])['structural_success_rate'], None)
