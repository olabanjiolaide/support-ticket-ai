"""Human-authored grouping of exact source fragments; no semantic inference."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .action_plan import SupportCategory
from .breakdown import preview

Category = SupportCategory | Literal['OUTSIDE_SCOPE', 'UNCLEAR']
Role = Literal['request', 'context', 'unclear', 'conditional', 'alternative', 'negated', 'resolved']
GroupId = Annotated[str, Field(pattern=r'^need-[1-9][0-9]{0,2}$')]
ACTIVE = {'request', 'unclear', 'conditional', 'alternative'}


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


class CustomerNeed(Strict):
    id: GroupId
    title: Annotated[str, Field(min_length=1, max_length=160)]
    category: Category

    @field_validator('title')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Enter a title for each need.')
        return value.strip()


class NeedReview(Strict):
    schema_version: Annotated[int, Field(ge=1, le=1)] = 1
    source_text: Annotated[str, Field(min_length=1, max_length=2000)]
    parts: Annotated[list[ReviewedFragment], Field(min_length=1, max_length=12)]
    groups: Annotated[list[CustomerNeed], Field(max_length=12)]
    clarification: Annotated[str, Field(max_length=600)] = ''

    @model_validator(mode='after')
    def evidence_and_groups(self):
        expected = preview(self.source_text)['parts']
        received = sorted(self.parts, key=lambda p: p.start)
        if [(p.id,p.start,p.end,p.text) for p in received] != [(p['id'],p['start'],p['end'],p['text']) for p in expected]:
            raise ValueError('Review must preserve every original preview fragment and its exact evidence.')
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
            if not any(p.group_id == group.id and p.role in ACTIVE for p in self.parts):
                raise ValueError('Each need must include a current or unresolved request; background alone is not a need.')
        if (any(p.role in {'unclear','conditional','alternative'} for p in self.parts)
                or any(g.category == 'UNCLEAR' for g in self.groups)) and not self.clarification.strip():
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
