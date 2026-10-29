"""Human-authored grouping of exact source fragments; no semantic inference."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .action_plan import SupportCategory
from .breakdown import preview

Category = SupportCategory | Literal['OUTSIDE_SCOPE', 'UNCLEAR']
Role = Literal['request', 'context', 'unclear', 'conditional', 'alternative', 'negated', 'resolved', 'obstacle']
GroupId = Annotated[str, Field(pattern=r'^need-[1-9][0-9]{0,2}$')]
ACTIVE = {'request', 'obstacle', 'unclear', 'conditional', 'alternative'}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ReviewedFragment(Strict):
    id: Annotated[str, Field(pattern=r'^part-[1-9][0-9]?$')]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    role: Role
    group_id: GroupId | None = None
    category: Category | None = None


class EvidenceTarget(Strict):
    text: Annotated[str, Field(min_length=1, max_length=300)]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]


class ReviewedAction(Strict):
    description: Annotated[str, Field(min_length=1, max_length=200)]
    target: EvidenceTarget | None = None

    @field_validator('description')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Describe the proposed action.')
        return value.strip()


class CustomerNeed(Strict):
    id: GroupId
    title: Annotated[str, Field(min_length=1, max_length=160)]
    category: Category
    kind: Literal['goal', 'obstacle', 'unclear'] = 'goal'
    actions: Annotated[list[ReviewedAction], Field(max_length=8)] = Field(default_factory=list)
    unknowns: Annotated[list[Annotated[str, Field(min_length=1, max_length=200)]], Field(max_length=8)] = Field(default_factory=list)

    @field_validator('unknowns')
    @classmethod
    def nonblank_unknowns(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError('Unknowns cannot be blank.')
        return [value.strip() for value in values]

    @field_validator('title')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Enter a title for each need.')
        return value.strip()


class NeedRelation(Strict):
    source: GroupId
    target: GroupId
    kind: Literal['may_block', 'depends_on', 'alternative_to']
    evidence_parts: Annotated[list[str], Field(min_length=1, max_length=24)]
    note: Annotated[str, Field(min_length=1, max_length=300)]


class NeedReview(Strict):
    schema_version: Annotated[int, Field(ge=1, le=3)] = 1
    source_text: Annotated[str, Field(min_length=1, max_length=2000)]
    parts: Annotated[list[ReviewedFragment], Field(min_length=1, max_length=24)]
    groups: Annotated[list[CustomerNeed], Field(max_length=12)]
    clarification: Annotated[str, Field(max_length=600)] = ''
    relations: Annotated[list[NeedRelation], Field(max_length=24)] = Field(default_factory=list)

    @model_validator(mode='after')
    def evidence_and_groups(self):
        received = sorted(self.parts, key=lambda p: p.start)
        if self.schema_version == 1:
            expected = preview(self.source_text)['parts']
            if [(p.id,p.start,p.end,p.text) for p in received] != [(p['id'],p['start'],p['end'],p['text']) for p in expected]:
                raise ValueError('Review must preserve every original preview fragment and its exact evidence.')
            if len(self.parts) > 12 or self.relations or any(g.kind != 'goal' for g in self.groups):
                raise ValueError('Editable evidence and relationships require schema version 2.')
        else:
            cursor = 0
            for index, part in enumerate(self.parts, start=1):
                if (part.id != f'part-{index}' or part.start < cursor or part.end <= part.start or
                        part.end > len(self.source_text) or self.source_text[cursor:part.start].strip() or
                        self.source_text[part.start:part.end] != part.text or not part.text.strip()):
                    raise ValueError('Evidence must preserve the original text in order, without overlaps or omissions.')
                cursor = part.end
            if self.source_text[cursor:].strip():
                raise ValueError('Evidence cannot omit the end of the original message.')
        ids = [g.id for g in self.groups]
        if len(ids) != len(set(ids)):
            raise ValueError('Need identifiers must be unique.')
        for p in self.parts:
            if p.group_id is not None and p.group_id not in ids:
                raise ValueError('Fragment refers to an unknown need.')
            if p.role in ACTIVE and p.group_id is None:
                raise ValueError('Assign each current or unresolved request to a need.')
            if p.category is not None and (p.role != 'request' or p.group_id is not None):
                raise ValueError('Grouped and non-request fragments use the need category, not a separate fragment category.')
        for group in self.groups:
            if self.schema_version < 3 and (group.actions or group.unknowns):
                raise ValueError('Actions, targets and unknowns require schema version 3.')
            for action in group.actions:
                target = action.target
                if target and (target.end <= target.start or target.end > len(self.source_text)
                               or self.source_text[target.start:target.end] != target.text or not target.text.strip()):
                    raise ValueError('Action targets must quote an exact range in the original message.')
            if not any(p.group_id == group.id and p.role in ACTIVE for p in self.parts):
                raise ValueError('Each need must include a current or unresolved request; background alone is not a need.')
        seen = set()
        dependencies = {group_id:set() for group_id in ids}
        for relation in self.relations:
            if relation.source not in ids or relation.target not in ids or relation.source == relation.target:
                raise ValueError('Relationships must connect two different existing needs.')
            key = (relation.source, relation.target, relation.kind)
            if key in seen or not relation.note.strip() or len(relation.evidence_parts) != len(set(relation.evidence_parts)):
                raise ValueError('Relationship must have distinct evidence, a note and no duplicate edge.')
            seen.add(key)
            evidence = [p for p in self.parts if p.id in relation.evidence_parts]
            if len(evidence) != len(relation.evidence_parts) or not {relation.source,relation.target}.issubset({p.group_id for p in evidence}):
                raise ValueError('Relationship evidence must reference source text assigned to both needs.')
            if relation.kind == 'depends_on': dependencies[relation.source].add(relation.target)
        visiting, visited = set(), set()
        def visit(node):
            if node in visiting: raise ValueError('Dependency relationships cannot contain a cycle.')
            if node not in visited:
                visiting.add(node)
                for target in dependencies[node]: visit(target)
                visiting.remove(node); visited.add(node)
        for group_id in ids: visit(group_id)
        if (self.relations or any(p.role in {'unclear','conditional','alternative'} for p in self.parts)
                or any(g.category == 'UNCLEAR' or g.kind == 'unclear' for g in self.groups)) and not self.clarification.strip():
            raise ValueError('Add a clarification question or relationship note for unresolved requests.')
        return self


class SaveNeedReview(Strict):
    version: Annotated[int, Field(ge=1)]
    actor: Annotated[str, Field(min_length=1, max_length=80)]
    review: NeedReview

    @field_validator('actor')
    @classmethod
    def reviewer(cls, value):
        if not value.strip():
            raise ValueError('Enter a reviewer label.')
        return value.strip()


class NeedProgress(Strict):
    version: Annotated[int, Field(ge=1)]
    actor: Annotated[str, Field(min_length=1, max_length=80)]
    need_id: GroupId
    status: Literal['open', 'in_progress', 'resolved', 'dismissed']
    note: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator('actor', 'note')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Enter a reviewer label and a note explaining this update.')
        return value.strip()
