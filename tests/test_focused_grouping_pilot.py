import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from support_ticket_ai import proposal_pilot
from support_ticket_ai.staged_proposals import StagedProposer, FOCUSED_ROLE_SYSTEM, ROLE_SYSTEM
from support_ticket_ai.proposals import ProposalFailure, align_plan
from support_ticket_ai.resources import data_path

class FocusedGroupingTests(unittest.TestCase):
    def test_constructor_keeps_baseline_and_validates_variant(self):
        self.assertEqual(StagedProposer('local').role_system,ROLE_SYSTEM)
        self.assertEqual(StagedProposer('local',role_prompt='focused').role_system,FOCUSED_ROLE_SYSTEM)
        with self.assertRaises(ValueError):StagedProposer('local',role_prompt='other')

    def test_cli_preserves_failures_and_records_focused_variant_and_suite(self):
        cases=json.loads(data_path('needs_role_contrasts.json').read_text())['cases']
        plans={c['text']:align_plan(c['text'],c['expected_plan']) for c in cases}
        class Fake:
            prompt_version=5
            def status(self):return {'available':True,'model':'local:latest','model_digest':'a'*64}
            def propose(self,text):
                if text==cases[0]['text']:raise ProposalFailure('invalid_output','Rejected',validation_code='relationship_invalid',attempts=2)
                return {'review':plans[text]}
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'report.json'
            args=['pilot','--model','local','--interpretation-mode','staged','--role-prompt','focused','--suite','role-contrasts','--output',str(output)]
            with patch('sys.argv',args),patch('support_ticket_ai.staged_proposals.StagedProposer',return_value=Fake()) as constructor:
                self.assertEqual(proposal_pilot.main(),0)
                constructor.assert_called_once_with('local',role_prompt='focused')
            report=json.loads(output.read_text())
            self.assertEqual(report['role_prompt'],'focused')
            self.assertEqual(report['attempted'],14)
            self.assertEqual(report['valid_structured_responses'],13)
            self.assertEqual(report['summary']['failed_responses'],1)
            self.assertEqual(report['cases'][0]['generation_attempts'],2)
            with patch('sys.argv',args),self.assertRaises(SystemExit):proposal_pilot.main()
