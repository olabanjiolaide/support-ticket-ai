"""Validate proposed support actions and exact text evidence; no inference or execution."""

import argparse
import json
from pathlib import Path
import sys
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CATEGORIES = frozenset({'ACCOUNT', 'CANCEL', 'CONTACT', 'DELIVERY', 'FEEDBACK', 'INVOICE',
                        'ORDER', 'PAYMENT', 'REFUND', 'SHIPPING', 'SUBSCRIPTION'})
Nonempty = Annotated[str, Field(min_length=1, max_length=2000)]
Identifier = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')]
SupportCategory = Literal['ACCOUNT', 'CANCEL', 'CONTACT', 'DELIVERY', 'FEEDBACK', 'INVOICE',
                          'ORDER', 'PAYMENT', 'REFUND', 'SHIPPING', 'SUBSCRIPTION']


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class EvidenceSpan(StrictRecord):
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]
    text: Nonempty

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start or not self.text.strip():
            raise ValueError('Evidence requires a nonempty, forward span.')
        return self


class ProposedAction(StrictRecord):
    action_id: Identifier
    description: Nonempty
    status: Literal['requested', 'negated', 'conditional', 'context', 'unclear']
    category: SupportCategory | None
    disposition: Literal['review', 'clarify', 'excluded']
    evidence: Annotated[list[EvidenceSpan], Field(min_length=1, max_length=8)]
    condition_evidence: Annotated[list[EvidenceSpan], Field(max_length=8)] = Field(default_factory=list)
    uncalibrated_score: Annotated[float, Field(ge=0, le=1)] | None = None

    @model_validator(mode='after')
    def coherent(self):
        if not self.description.strip():
            raise ValueError('Action description cannot be blank.')
        if self.category is not None and self.category not in CATEGORIES:
            raise ValueError('Category is outside the Bitext support taxonomy.')
        expected = ('excluded' if self.status in ('negated', 'context') else
                    'clarify' if self.status in ('conditional', 'unclear') or self.category is None else 'review')
        if self.disposition != expected:
            raise ValueError('Disposition conflicts with action status or unresolved category.')
        if bool(self.condition_evidence) != (self.status == 'conditional'):
            raise ValueError('Conditional actions require condition evidence; other statuses cannot attach it.')
        return self


class ActionRelation(StrictRecord):
    source_action_id: Identifier
    target_action_id: Identifier
    kind: Literal['depends_on', 'alternative_to']
    evidence: Annotated[list[EvidenceSpan], Field(min_length=1, max_length=8)]


class ActionPlan(StrictRecord):
    schema_version: Literal[1]
    taxonomy_id: Literal['bitext-support-v1']
    offset_unit: Literal['unicode_code_points']
    source_text: Annotated[str, Field(min_length=1, max_length=2000)]
    outcome: Literal['actions_proposed', 'needs_clarification', 'unsupported']
    actions: Annotated[list[ProposedAction], Field(max_length=20)]
    relations: Annotated[list[ActionRelation], Field(max_length=40)] = Field(default_factory=list)
    clarification_question: Nonempty | None = None
    requires_human_review: Literal[True]
    # Authored examples are marked as such; no inference provenance is fabricated.
    origin: Literal['authored_example', 'model_proposal']
    model_sha256: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')] | None = None

    @field_validator('schema_version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('Schema version must be integer 1.')
        return value

    @field_validator('requires_human_review', mode='before')
    @classmethod
    def strict_review(cls, value):
        if value is not True:
            raise ValueError('Human review must be explicitly true.')
        return value

    @model_validator(mode='after')
    def consistent(self):
        if not self.source_text.strip():
            raise ValueError('Source text cannot be blank; offsets refer to the unchanged input.')
        if (self.origin == 'model_proposal') != (self.model_sha256 is not None):
            raise ValueError('Only model proposals require a model fingerprint.')
        ids = [action.action_id for action in self.actions]
        if len(ids) != len(set(ids)):
            raise ValueError('Action IDs must be unique.')
        edges = set()
        dependencies = {key: set() for key in ids}
        for relation in self.relations:
            a, b, kind = relation.source_action_id, relation.target_action_id, relation.kind
            if a not in dependencies or b not in dependencies or a == b:
                raise ValueError('Relation must reference two different existing actions.')
            edge = (min(a, b), max(a, b), kind) if kind == 'alternative_to' else (a, b, kind)
            if edge in edges:
                raise ValueError('Duplicate relation.')
            edges.add(edge)
            if kind == 'depends_on':
                dependencies[a].add(b)
        visiting, visited = set(), set()
        def visit(node):
            if node in visiting:
                raise ValueError('Dependency relations cannot contain a cycle.')
            if node not in visited:
                visiting.add(node)
                for target in dependencies[node]:
                    visit(target)
                visiting.remove(node)
                visited.add(node)
        for node in ids:
            visit(node)
        for action in self.actions:
            self.check_spans(action.evidence)
            self.check_spans(action.condition_evidence)
        for relation in self.relations:
            self.check_spans(relation.evidence)
        question = self.clarification_question
        if question is not None and not question.strip():
            raise ValueError('Clarification question cannot be blank.')
        needs_clarification = any(a.disposition == 'clarify' for a in self.actions) or bool(self.relations)
        # Relations require review of coordination/conditions rather than suggesting execution order.
        if self.outcome == 'unsupported':
            if self.actions or self.relations or question is not None:
                raise ValueError('Unsupported plans cannot propose actions or clarification.')
        elif self.outcome == 'needs_clarification':
            if question is None:
                raise ValueError('Clarification outcome requires a question.')
        elif (needs_clarification or question is not None or
              not any(a.disposition == 'review' for a in self.actions)):
            raise ValueError('Proposed-action outcome requires a reviewable action and no unresolved coordination.')
        return self

    def check_spans(self, spans):
        seen = set()
        for span in spans:
            if (span.start, span.end) in seen:
                raise ValueError('Duplicate evidence span within a field.')
            seen.add((span.start, span.end))
            if self.source_text[span.start:span.end] != span.text or span.end > len(self.source_text):
                raise ValueError('Evidence must match the original source text at the exact offsets.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--file', type=Path)
    choice.add_argument('--schema', action='store_true')
    args = parser.parse_args()
    try:
        if args.schema:
            print(json.dumps(ActionPlan.model_json_schema(), indent=2))
        else:
            plan = ActionPlan.model_validate_json(args.file.read_bytes())
            print(json.dumps({'valid': True, 'outcome': plan.outcome, 'actions': len(plan.actions),
                              'requires_human_review': plan.requires_human_review}))
    except (OSError, ValidationError) as error:
        # Do not echo submitted source text in a failed validation message.
        print(f'Invalid action-plan file ({type(error).__name__}).', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
