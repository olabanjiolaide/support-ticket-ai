"""Bounded, unreviewed workspace drafts; never a confirmed interpretation."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .need_review import (Strict, Category, GroupId, Role, EvidenceTarget, NeedRelation, NeedReview)


class DraftAction(Strict):
    description: Annotated[str, Field(max_length=200)] = ''
    target: EvidenceTarget | None = None


class DraftNeed(Strict):
    id: GroupId
    title: Annotated[str, Field(max_length=160)] = ''
    category: Category | Literal[''] | None = None
    kind: Literal['goal','obstacle','unclear'] = 'goal'
    actions: Annotated[list[DraftAction], Field(max_length=8)] = Field(default_factory=list)
    unknowns: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=8)] = Field(default_factory=list)


class DraftFragment(Strict):
    id: Annotated[str, Field(pattern=r'^part-[1-9][0-9]?$')]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]
    text: Annotated[str, Field(min_length=1,max_length=2000)]
    role: Role | Literal['unconfirmed']
    group_id: GroupId | None = None
    category: Category | Literal[''] | None = None


class DraftPlan(Strict):
    schema_version: Literal[3] = 3
    source_text: Annotated[str, Field(min_length=1,max_length=2000)]
    parts: Annotated[list[DraftFragment], Field(min_length=1,max_length=24)]
    groups: Annotated[list[DraftNeed], Field(max_length=12)]
    relations: Annotated[list[NeedRelation], Field(max_length=24)] = Field(default_factory=list)
    clarification: Annotated[str, Field(max_length=600)] = ''

    @model_validator(mode='after')
    def exact_draft(self):
        cursor=0
        for index,part in enumerate(self.parts,1):
            if (part.id!=f'part-{index}' or part.start<cursor or part.end<=part.start or part.end>len(self.source_text)
                or self.source_text[cursor:part.start].strip() or self.source_text[part.start:part.end]!=part.text or not part.text.strip()):
                raise ValueError('Draft evidence must preserve the original message in order.')
            cursor=part.end
        if self.source_text[cursor:].strip():
            raise ValueError('Draft evidence cannot omit the original message.')
        ids=[g.id for g in self.groups]
        if len(ids)!=len(set(ids)) or any(p.group_id is not None and p.group_id not in ids for p in self.parts):
            raise ValueError('Draft need references must be consistent.')
        parts={p.id for p in self.parts}
        for relation in self.relations:
            if relation.source not in ids or relation.target not in ids or any(p not in parts for p in relation.evidence_parts):
                raise ValueError('Draft relationship references must exist.')
        for group in self.groups:
            for action in group.actions:
                target=action.target
                if target and (target.end<=target.start or target.end>len(self.source_text)
                               or self.source_text[target.start:target.end]!=target.text or not target.text.strip()):
                    raise ValueError('Draft action targets must quote the original message.')
        return self


class NeedsDraft(Strict):
    schema_version: Literal[1] = 1
    editable: DraftPlan | None = None
    proposed: NeedReview | None = None
    model_draft: bool = False
    proposal_adopted: bool = False

    @model_validator(mode='after')
    def same_source(self):
        if self.editable is None and self.proposed is None:
            raise ValueError('A needs draft must contain editable evidence or a proposal.')
        if self.editable and self.proposed and self.editable.source_text!=self.proposed.source_text:
            raise ValueError('Draft and proposal must refer to the same original message.')
        if self.proposal_adopted and (self.editable is None or self.proposed is None):
            raise ValueError('An adopted proposal needs its proposal and editable draft.')
        if self.model_draft and self.editable is None:
            raise ValueError('An adopted model draft must include editable evidence.')
        return self

    @property
    def source_text(self):
        return self.editable.source_text if self.editable else self.proposed.source_text
