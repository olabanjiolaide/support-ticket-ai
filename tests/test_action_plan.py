import copy
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from support_ticket_ai.action_plan import ActionPlan, main
from support_ticket_ai.resources import data_path


class ActionPlanTests(unittest.TestCase):
    def example(self):
        return json.loads(data_path('action_plan_example.json').read_text())

    def test_authored_example_and_published_schema_match_contract(self):
        plan = ActionPlan.model_validate(self.example())
        self.assertEqual([a.category for a in plan.actions], ['ACCOUNT', 'REFUND'])
        self.assertEqual(json.loads(data_path('action_plan_schema.json').read_text()), ActionPlan.model_json_schema())
        self.assertTrue(plan.requires_human_review)
        self.assertIsNone(plan.model_sha256)

    def test_offsets_preserve_original_unicode_and_exact_text(self):
        value = self.example()
        value['source_text'] = '💳 ' + value['source_text']
        for action in value['actions']:
            for span in action['evidence']:
                span['start'] += 2
                span['end'] += 2
        ActionPlan.model_validate(value)
        for field, replacement in [('text', 'invented evidence'), ('end', 2001), ('start', 1)]:
            invalid = copy.deepcopy(value)
            invalid['actions'][0]['evidence'][0][field] = replacement
            with self.assertRaises(ValidationError):
                ActionPlan.model_validate(invalid)

    def test_negated_context_and_conditional_actions_cannot_be_treated_as_ready(self):
        for status in ('negated', 'context', 'conditional', 'unclear'):
            value = self.example()
            value['actions'][0]['status'] = status
            with self.assertRaises(ValidationError):
                ActionPlan.model_validate(value)
        for status in ('negated', 'context'):
            value = self.example()
            value['actions'][0].update(status=status, disposition='excluded')
            ActionPlan.model_validate(value)
        value = self.example()
        value['outcome'] = 'needs_clarification'
        value['clarification_question'] = 'Should the account change be handled first?'
        value['actions'][0].update(status='conditional', disposition='clarify',
                                  condition_evidence=value['actions'][0]['evidence'])
        ActionPlan.model_validate(value)  # Structural validation cannot verify condition semantics.

    def test_duplicate_actions_unknown_relations_cycles_and_forged_spans_rejected(self):
        value = self.example()
        value['actions'][1]['action_id'] = value['actions'][0]['action_id']
        with self.assertRaises(ValidationError):
            ActionPlan.model_validate(value)
        relation = {'source_action_id': 'action-1', 'target_action_id': 'action-2',
                    'kind': 'depends_on', 'evidence': self.example()['actions'][0]['evidence']}
        for relations in ([{**relation, 'target_action_id': 'absent'}],
                          [{**relation, 'target_action_id': 'action-1'}],
                          [relation, relation],
                          [relation, {**relation, 'source_action_id': 'action-2', 'target_action_id': 'action-1'}]):
            value = self.example()
            value.update(outcome='needs_clarification', clarification_question='Which action should come first?', relations=relations)
            with self.assertRaises(ValidationError):
                ActionPlan.model_validate(value)

    def test_unknown_categories_coercion_nonfinite_scores_and_extra_fields_rejected(self):
        for key, bad in [('schema_version', True), ('schema_version', 1.0),
                         ('requires_human_review', False), ('requires_human_review', 1),
                         ('execute_now', True)]:
            value = self.example()
            value[key] = bad
            with self.assertRaises(ValidationError):
                ActionPlan.model_validate(value)
        for field, bad in [('category', 'BILLING'), ('uncalibrated_score', float('nan')),
                           ('uncalibrated_score', float('inf'))]:
            value = self.example()
            value['actions'][0][field] = bad
            with self.assertRaises(ValidationError):
                ActionPlan.model_validate(value)

    def test_model_proposals_require_provenance_and_unresolved_routes_need_clarification(self):
        value = self.example()
        value['origin'] = 'model_proposal'
        with self.assertRaises(ValidationError):
            ActionPlan.model_validate(value)
        value['model_sha256'] = 'a' * 64
        ActionPlan.model_validate(value)
        value['actions'][0].update(category=None, disposition='clarify')
        with self.assertRaises(ValidationError):
            ActionPlan.model_validate(value)
        value.update(outcome='needs_clarification', clarification_question='What should be changed?')
        ActionPlan.model_validate(value)

    def test_cli_error_does_not_echo_source_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            path.write_text('{"source_text":"private-message"}')
            errors = io.StringIO()
            with patch('sys.argv', ['action-plan', '--file', str(path)]), redirect_stderr(errors):
                self.assertEqual(main(), 1)
            self.assertNotIn('private-message', errors.getvalue())
