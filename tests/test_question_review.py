import copy
import unittest
from support_ticket_ai.question_review import worksheet, summarize_review

class QuestionReviewTests(unittest.TestCase):
    def report(self):
        return {'evaluation_mode':'combined_conditions_questions','cases':[
            {'id':'choice','valid_structured_response':True,'proposal':{'review':{'source_text':'Cancel A or keep A.'},'question':{'decision':'ask','text':'Which order should I cancel?'}}},
            {'id':'clear','valid_structured_response':True,'proposal':{'review':{'source_text':'Send invoice.'},'question':{'decision':'none','text':''}}},
            {'id':'failed','valid_structured_response':False,'failure_code':'timeout'}]}

    def test_pending_and_failures_never_pass(self):
        report=self.report(); review=worksheet(report,'digest')
        totals=summarize_review(report,'digest',review)['summary']
        self.assertEqual((totals['unreviewed_valid'],totals['generation_failures'],totals['all_criteria_passed']),(2,1,0))

    def test_human_rejects_wording_despite_ask_decision(self):
        report=self.report();review=worksheet(report,'digest')
        entry=review['cases'][0]['review'];entry['reviewer']='Reviewer'
        entry['ratings']={key:'pass' for key in entry['ratings']}
        entry['ratings']['preserves_actions_and_targets']='fail'
        totals=summarize_review(report,'digest',review)['summary']
        self.assertEqual(totals['reviewed_valid'],1)
        self.assertEqual(totals['all_criteria_passed'],0)
        self.assertEqual(totals['criteria_failures']['preserves_actions_and_targets'],1)

    def test_none_requires_explicit_applicability_and_reviewer(self):
        report=self.report();review=worksheet(report,'digest');entry=review['cases'][1]['review']
        entry['ratings']={key:'not_applicable' for key in entry['ratings']}
        entry['ratings']['decision_appropriate']='pass'
        self.assertEqual(summarize_review(report,'digest',review)['summary']['reviewed_valid'],0)
        entry['reviewer']='Reviewer'
        self.assertEqual(summarize_review(report,'digest',review)['summary']['all_criteria_passed'],1)

    def test_source_binding_and_invalid_ratings(self):
        report=self.report();base=worksheet(report,'digest')
        for change in ['hash','text','missing','rating','failed']:
            review=copy.deepcopy(base)
            if change=='hash':review['report_sha256']='different'
            if change=='text':review['cases'][0]['question']['text']='Rewritten question'
            if change=='missing':review['cases'].pop()
            if change=='rating':review['cases'][0]['review']['ratings']['resolves_ambiguity']='not_applicable'
            if change=='failed':review['cases'][2]['review']['ratings']['decision_appropriate']='pass'
            with self.subTest(change=change),self.assertRaises(ValueError):summarize_review(report,'digest',review)
