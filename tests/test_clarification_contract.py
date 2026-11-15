import unittest
from support_ticket_ai.clarification_pilot import decision_schema,validate_decision
from support_ticket_ai.proposal_evidence import source_fragments
from support_ticket_ai.proposals import ProposalFailure

class ClarificationContractTests(unittest.TestCase):
    def test_branches_constrain_each_decision_and_original_is_available(self):
        evidence=source_fragments('Find order A. Check my refund.')
        self.assertIn('properties',decision_schema(evidence,'baseline'))
        branches=decision_schema(evidence,'constrained')['anyOf']
        none,ask,note=[b['properties'] for b in branches]
        self.assertEqual(none['text']['maxLength'],0)
        self.assertEqual(none['evidence_parts']['maxItems'],0)
        self.assertEqual(ask['reason']['enum'],['ambiguous_target','alternative_choice','unclear_meaning'])
        self.assertEqual(note['reason']['enum'],['conditional_instruction'])
        self.assertEqual(note['evidence_parts']['minItems'],1)
        self.assertEqual(note['evidence_parts']['items']['enum'],['part-1','part-2'])
        self.assertNotIn('anyOf',decision_schema(evidence,'baseline'))

    def test_safe_diagnostics_distinguish_none_payload_and_missing_support(self):
        evidence=source_fragments('Find my order number.')
        for raw,rule in [({'decision':'none','reason':'none','evidence_parts':['part-1'],'text':'private customer text'},'none_payload'),({'decision':'ask','reason':'ambiguous_target','evidence_parts':[],'text':''},'missing_support'),({'decision':'note','reason':'ambiguous_target','evidence_parts':['part-1'],'text':'private customer text'},'note_reason')]:
            with self.assertRaises(ProposalFailure) as caught:validate_decision(raw,evidence)
            self.assertEqual(caught.exception.diagnostics['violations'][0]['rule'],rule)
            self.assertNotIn('private customer text',str(caught.exception.diagnostics))

    def test_unknown_extra_field_name_is_not_echoed(self):
        raw={'decision':'none','reason':'none','evidence_parts':[],'text':'','private-key':42}
        with self.assertRaises(ProposalFailure) as caught:validate_decision(raw,source_fragments('Help.'))
        self.assertNotIn('private-key',str(caught.exception.diagnostics))
