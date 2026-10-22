"""Evidence integrity and service isolation for the review preview."""
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from support_ticket_ai.api import create_app
from support_ticket_ai.breakdown import preview


class BreakdownTests(TestCase):
    def test_exact_unicode_evidence_and_no_nonwhite_text_lost(self):
        text = '  👩🏿‍💻 Can I get offers?\nMy packages await delivery. I need my invoice and I cannot log in.  '
        result = preview(text)
        self.assertEqual(result['source_text'], text)
        self.assertEqual(result['offset_unit'], 'unicode_code_points')
        self.assertFalse(result['semantic_interpretation'])
        self.assertTrue(result['requires_human_review'])
        coverage = set()
        for part in result['parts']:
            self.assertEqual(text[part['start']:part['end']],part['text'])
            self.assertEqual(part['role'],'unconfirmed')
            self.assertNotIn('suggested_category',part)
            indices=set(range(part['start'],part['end']))
            self.assertFalse(coverage & indices)
            coverage |= indices
        self.assertTrue(all(index in coverage for index,char in enumerate(text) if not char.isspace()))
        self.assertEqual(len(result['parts']),4)

    def test_grouped_tail_keeps_all_text(self):
        text = ' '.join(f'Question {i}?' for i in range(30))
        result = preview(text)
        self.assertEqual(len(result['parts']),12)
        self.assertTrue(result['grouped_remainder'])
        self.assertTrue(result['parts'][-1]['text'].endswith('Question 29?'))

    def test_conditions_and_background_are_never_declared_independent_intents(self):
        for text in ['If it cannot arrive tomorrow, cancel it or refund me.',
                     'I do not want a refund. My parcel arrived.',
                     'Write a poem about invoices and payment.',
                     'I have see my order history. How do I get it back?']:
            result=preview(text)
            self.assertTrue(all(p['role']=='unconfirmed' for p in result['parts']))
            self.assertEqual(result['source_text'],text)
        self.assertTrue(preview('If it fails, refund me instead.')['parts'][0]['coordination_cue'])

    def test_no_model_or_database_required_and_no_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(requests_db=Path(directory)/'local.sqlite3')) as client:
                with patch('support_ticket_ai.predict.TicketPredictor.predict',side_effect=AssertionError('Must not infer')):
                    response=client.post('/breakdown',json={'text':'Can I get offers? My packages await delivery.'})
                    self.assertEqual(response.status_code,200)
                self.assertEqual(client.get('/requests/overview').json()['total'],0)
                self.assertEqual(client.post('/predict',json={'text':'invoice'}).status_code,503)
                self.assertEqual(client.get('/assets/breakdown.js').status_code,200)

    def test_reject_invalid_input_without_echoing_text(self):
        with TestClient(create_app()) as client:
            for body in [{'text':''},{'text':'  '},{'text':'x'*2001},{'text':123},
                         {'text':'private text','model':'secret'}, {'text':None}]:
                response=client.post('/breakdown',json=body)
                self.assertEqual(response.status_code,422)
                self.assertNotIn('private text',response.text)
            self.assertEqual(client.post('/breakdown',json={'text':'x'*2000}).status_code,200)
