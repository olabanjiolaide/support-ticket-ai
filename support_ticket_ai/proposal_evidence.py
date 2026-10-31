"""Bounded, deterministic source excerpts for proposal references, not detected intents."""
import re
from .breakdown import BreakdownRequest, BOUNDARY

EVIDENCE_VERSION = 1
MAX_FRAGMENTS = 24
# Keep conjunctions as evidence. This English heuristic proposes boundaries only.
COORDINATION = re.compile(r'\s+(?=(?:and\s+(?:also\b|please\b|check\b|send\b|cancel\b|keep\b)|but\s+(?:I|we|my|our)\b|however\b))', re.I)


def source_fragments(text):
    text = BreakdownRequest(text=text).text
    cuts = sorted({(m.start(), m.end()) for pattern in (BOUNDARY, COORDINATION) for m in pattern.finditer(text)})
    # Overlapping whitespace matches represent the same boundary.
    boundaries = []
    for start, end in cuts:
        if boundaries and start < boundaries[-1][1]:
            boundaries[-1] = (boundaries[-1][0], max(end, boundaries[-1][1]))
        else:
            boundaries.append((start, end))
    selected = boundaries[:MAX_FRAGMENTS - 1]
    starts = [0] + [end for _, end in selected]
    ends = [start for start, _ in selected] + [len(text)]
    fragments = []
    for start, end in zip(starts, ends):
        while start < end and text[start].isspace(): start += 1
        while end > start and text[end - 1].isspace(): end -= 1
        if start == end: continue
        fragments.append({'id': f'part-{len(fragments)+1}', 'start': start, 'end': end, 'text': text[start:end]})
    return {'version': EVIDENCE_VERSION, 'method': 'numbered_punctuation_and_coordination',
            'offset_unit': 'unicode_code_points', 'fragments': fragments,
            'grouped_remainder': len(boundaries) >= MAX_FRAGMENTS,
            'limitations': 'Deterministic excerpts are not detected needs. A fragment can contain multiple needs. Review and edit boundaries; meaning and relationships remain unverified.'}
