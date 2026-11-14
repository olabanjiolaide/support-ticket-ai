import unittest
from support_ticket_ai.fragment_pilot import score
from test_staged_proposals import StagedTests,FIRST

class FragmentPilotTests(unittest.TestCase):
    run_model = StagedTests.run_model
    def test_demoted_request_still_counts_as_category_error(self):
        expected=FIRST['fragments']
        actual=[dict(p) for p in expected];actual[1].update(role='context',category=None)
        result=score(expected,actual)
        self.assertEqual(result['active_category_errors'],1)
        self.assertEqual(result['active_demoted_to_background'],1)
        self.assertEqual(result['role_errors'],1)

    def test_consistency_failure_reports_outer_attempt(self):
        from support_ticket_ai.proposals import ProposalFailure
        from test_staged_proposals import SECOND
        import copy
        bad=copy.deepcopy(SECOND);bad['segments'][1]['role']='context'
        with self.assertRaises(ProposalFailure) as caught:self.run_model(second=bad)
        self.assertEqual(caught.exception.attempts,1)
