"""Deterministic evidence segmentation for a human-assisted preview, not intent inference."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Annotated

VERSION = 1
MAX_PARTS = 12
# Keep punctuation and conjunctions in the source evidence. No text rewriting.
BOUNDARY = re.compile(r'(?<=[.!?;])\s+|\n+|\s+(?=and\s+(?:(?:I|we|my|our)\b|(?:can|could|would)\s+you\b))', re.I)
RELATION = re.compile(r'\b(?:if|unless|either|or|instead|otherwise|rather\s+than|only\s+after)\b', re.I)


class BreakdownRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: Annotated[str, Field(strict=True, min_length=1, max_length=2000)]

    @field_validator('text')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Message cannot be blank.')
        return value  # Offsets refer to the original, including leading whitespace.


def preview(text: str) -> dict:
    text = BreakdownRequest(text=text).text
    boundaries = list(BOUNDARY.finditer(text))
    starts = [0] + [match.end() for match in boundaries[:MAX_PARTS - 1]]
    ends = [match.start() for match in boundaries[:MAX_PARTS - 1]] + [len(text)]
    parts = []
    for start, end in zip(starts, ends):
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start == end:
            continue
        evidence = text[start:end]
        parts.append({'id': f'part-{len(parts) + 1}', 'start': start, 'end': end,
                      'text': evidence, 'role': 'unconfirmed',
                      'coordination_cue': bool(RELATION.search(evidence))})
    return {'version': VERSION, 'method': 'punctuation_and_coordination_rules',
            'offset_unit': 'unicode_code_points', 'source_text': text,
            'requires_human_review': True, 'semantic_interpretation': False,
            'grouped_remainder': len(boundaries) >= MAX_PARTS,
            'parts': parts,
            'limitations': 'Fragments are not detected intents. Review boundaries, context, negation, references and relationships against the full message. No needs, eligibility or customer facts are inferred.'}
