import json
import unittest
from unittest.mock import patch
import httpx
from support_ticket_ai.resources import data_path
from support_ticket_ai.proposals import align_plan
from support_ticket_ai.proposal_evidence import source_fragments
from support_ticket_ai.staged_proposals import StagedProposer,ROLE_SYSTEM,FOCUSED_ROLE_SYSTEM
from support_ticket_ai.fragment_pilot import classify

class RoleContrastTests(unittest.TestCase):
    def test_contrast_fixtures_preserve_original_evidence_and_baseline_cases(self):
        cases=json.loads(data_path('needs_role_contrasts.json').read_text())['cases']
        baseline=json.loads(data_path('needs_evidence_regressions.json').read_text())['cases']
        self.assertEqual(cases[:8],baseline)
        self.assertEqual(len(cases),14)
        self.assertEqual(len({c['id'] for c in cases}),14)
        for c in cases:
            review=align_plan(c['text'],c['expected_plan'])
            self.assertEqual([p['text'] for p in review['parts']],[p['text'] for p in source_fragments(c['text'])['fragments']])

    def test_variant_changes_only_system_prompt_and_not_evidence_or_output(self):
        original=httpx.Client;chats=[]
        def handler(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'local:latest','digest':'a'*64,'details':{'format':'gguf'}}]})
            chats.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps({'fragments':[{'fragment_id':'part-1','role':'negated','category':None}]})}})
        with patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            engine=StagedProposer('local');before=classify(engine,'Do not refund it.')
            engine.role_system=FOCUSED_ROLE_SYSTEM;after=classify(engine,'Do not refund it.')
        self.assertEqual(before,after)
        self.assertEqual(chats[0]['format'],chats[1]['format'])
        self.assertEqual(chats[0]['messages'][1],chats[1]['messages'][1])
        self.assertNotEqual(chats[0]['messages'][0],chats[1]['messages'][0])
        self.assertEqual(StagedProposer('local').role_system,ROLE_SYSTEM)
