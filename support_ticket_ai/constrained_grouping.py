"""Source-keyed membership schema; no silent assignment or label repair."""
import hashlib
import json
from typing import Annotated
from pydantic import Field, ValidationError
from .need_review import Strict, GroupId
from .compact_grouping import CompactStagedProposer, GroupTitle, ACTIVE, expand_memberships, COMPACT_SYSTEM
from .proposals import ProposalFailure

CONSTRAINED_SYSTEM = COMPACT_SYSTEM.replace(
    'Return every fragment_id exactly once, in original order, with group_id or null.',
    'Return assignments as an object keyed by every supplied fragment_id, with group ID or null as each value. Active fragments require a non-null group ID.')
CONSTRAINED_SYSTEM = CONSTRAINED_SYSTEM.replace('memberships, groups, clarification.', 'assignments, groups, clarification.')

class AssignmentPlan(Strict):
    assignments: dict[str,GroupId | None]
    groups: Annotated[list[GroupTitle],Field(max_length=12)]
    clarification: Annotated[str,Field(max_length=600)]


def assignment_schema(meanings):
    schema=AssignmentPlan.model_json_schema()
    properties={}
    for meaning in meanings.fragments:
        group={'type':'string','pattern':r'^need-[1-9][0-9]{0,2}$'}
        properties[meaning.fragment_id]=group if meaning.role in ACTIVE else {'anyOf':[group,{'type':'null'}]}
    schema['properties']['assignments']={'type':'object','properties':properties,
        'required':list(properties),'additionalProperties':False}
    return schema


def expand_assignments(meanings,raw):
    try:
        plan=AssignmentPlan.model_validate(raw)
    except ValidationError as error:
        raise ProposalFailure('invalid_output','Source-keyed assignments failed validation.',validation_code='schema_invalid') from error
    ids=[p.fragment_id for p in meanings.fragments]
    if set(plan.assignments)!=set(ids):
        raise ProposalFailure('invalid_output','Assignments must cover exactly the supplied fragment IDs.',validation_code='fragment_coverage')
    # JSON object order is immaterial; restore source order using server-owned IDs.
    converted={'memberships':[{'fragment_id':id,'group_id':plan.assignments[id]} for id in ids],
               'groups':[g.model_dump(mode='json') for g in plan.groups],'clarification':plan.clarification}
    return expand_memberships(meanings,converted)


class ConstrainedStagedProposer(CompactStagedProposer):
    grouping_system=CONSTRAINED_SYSTEM

    def __init__(self,model,*,role_prompt='baseline'):
        super().__init__(model,role_prompt=role_prompt)
        self.prompt_version=7

    def membership_schema(self,meanings):
        return assignment_schema(meanings)

    def expand_response(self,meanings,raw):
        return expand_assignments(meanings,raw)

    def propose(self,text):
        result=super().propose(text)
        result.update(prompt_version=7,grouping_contract='constrained',
            prompt_sha256=hashlib.sha256((CONSTRAINED_SYSTEM+json.dumps(AssignmentPlan.model_json_schema(),sort_keys=True)+result['prompt_sha256']).encode()).hexdigest())
        return result
