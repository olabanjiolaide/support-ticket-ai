"""Evidence-based development diagnostics, not a semantic ground-truth judge.

Match needs one-to-one by active non-whitespace source-character IoU >= 0.5.
Maximize matched count first and total overlap second. Matching ignores category
and kind so those errors remain visible rather than being counted as omissions.
"""
from functools import lru_cache

ACTIVE = {'request', 'obstacle', 'unclear', 'conditional', 'alternative'}


def evidence(document, group_id=None, parts=None, active_only=False):
    return frozenset(i for part in document['parts']
                     if (group_id is None or part.get('group_id') == group_id)
                     and (parts is None or part['id'] in parts)
                     and (not active_only or part['role'] in ACTIVE)
                     for i in range(part['start'], part['end'])
                     if not document['source_text'][i].isspace())


def compare(expected, actual):
    if expected['source_text'] != actual['source_text']:
        raise ValueError('Compare plans for exactly the same original message.')
    if max(len(expected['groups']), len(actual['groups'])) > 12:
        raise ValueError('At most 12 needs per plan are supported.')
    eg, ag = expected['groups'], actual['groups']
    ee = [evidence(expected, g['id'], active_only=True) for g in eg]
    ae = [evidence(actual, g['id'], active_only=True) for g in ag]
    overlaps = [[len(e & a) / len(e | a) if e | a else 0 for a in ae] for e in ee]

    @lru_cache(None)
    def match(index, used):
        if index == len(eg):
            return (0, 0.0, ())
        count, total, pairs = match(index + 1, used)
        best = (count, total, pairs)
        for j, score in enumerate(overlaps[index]):
            if score < 0.5 or used & (1 << j):
                continue
            n, weight, tail = match(index + 1, used | (1 << j))
            candidate = (n + 1, weight + score, ((index, j),) + tail)
            if candidate[:2] > best[:2]:
                best = candidate
        return best

    matched, _, pairs = match(0, 0)
    mapping = {eg[i]['id']: ag[j]['id'] for i, j in pairs}
    def role_map(document):
        return {i: p['role'] for p in document['parts']
                for i in range(p['start'], p['end']) if not document['source_text'][i].isspace()}
    er, ar = role_map(expected), role_map(actual)
    indices = [i for i, c in enumerate(expected['source_text']) if not c.isspace()]
    confusion = {}
    for i in indices:
        key = f"{er.get(i, 'missing')}->{ar.get(i, 'missing')}"
        confusion[key] = confusion.get(key, 0) + 1
    def edges(document, translate=None):
        found = set()
        for relation in document.get('relations', []):
            source, target = relation['source'], relation['target']
            if translate is not None:
                if source not in translate or target not in translate:
                    # Unmatched endpoints cannot match a predicted edge.
                    source, target = f'expected:{source}', f'expected:{target}'
                else:
                    source, target = translate[source], translate[target]
            if relation['kind'] == 'alternative_to':
                source, target = sorted((source, target))
            found.add((source, target, relation['kind']))
        return found
    expected_edges, actual_edges = edges(expected, mapping), edges(actual)
    def relation_evidence(document, translate=None):
        result = {}
        for relation in document.get('relations', []):
            mini = {**document, 'relations': [relation]}
            key = next(iter(edges(mini, translate)))
            result[key] = evidence(document, parts=relation['evidence_parts'])
        return result
    expected_support, actual_support = relation_evidence(expected, mapping), relation_evidence(actual)
    return {
        # Retain original pilot fields for report consumers.
        'category_set_match': {g['category'] for g in eg} == {g['category'] for g in ag},
        'need_count_match': len(eg) == len(ag),
        'non_whitespace_role_character_agreement': sum(er.get(i) == ar.get(i) for i in indices) / len(indices) if indices else 1.0,
        'relation_kind_set_match': {r['kind'] for r in expected.get('relations', [])} == {r['kind'] for r in actual.get('relations', [])},
        'expected_needs': len(eg), 'proposed_needs': len(ag), 'matched_needs': matched,
        'missed_needs': len(eg) - matched, 'extra_needs': len(ag) - matched,
        'matched_category_errors': sum(eg[i]['category'] != ag[j]['category'] for i, j in pairs),
        'matched_kind_errors': sum(eg[i].get('kind', 'goal') != ag[j].get('kind', 'goal') for i, j in pairs),
        'negated_or_resolved_as_active_characters': sum(er.get(i) in {'negated', 'resolved'} and ar.get(i) in ACTIVE for i in indices),
        'role_character_confusion': confusion,
        'correct_relation_edges': len(expected_edges & actual_edges),
        'missing_relation_edges': len(expected_edges - actual_edges),
        'extra_relation_edges': len(actual_edges - expected_edges),
        'matched_relation_evidence_errors': sum(expected_support[key] != actual_support[key] for key in expected_edges & actual_edges),
        'matched_evidence': [{'expected': eg[i]['id'], 'actual': ag[j]['id'], 'active_character_iou': overlaps[i][j]} for i, j in pairs],
    }


def summarize(rows):
    valid = [row['metrics'] for row in rows if row['valid_structured_response']]
    times = sorted(row['elapsed_seconds'] for row in rows)
    counts = ['expected_needs', 'proposed_needs', 'matched_needs', 'missed_needs', 'extra_needs',
              'matched_category_errors', 'matched_kind_errors', 'negated_or_resolved_as_active_characters',
              'correct_relation_edges', 'missing_relation_edges', 'extra_relation_edges', 'matched_relation_evidence_errors']
    return {'attempted': len(rows), 'valid_structured_responses': len(valid),
            'failed_responses': len(rows) - len(valid),
            'structural_success_rate': len(valid) / len(rows) if rows else None,
            'valid_response_totals': {key: sum(m[key] for m in valid) for key in counts},
            'mean_elapsed_seconds_all_attempts': sum(times) / len(times) if times else None,
            'p95_elapsed_seconds_all_attempts': times[max(0, (95 * len(times) + 99) // 100 - 1)] if times else None,
            'quality_denominator': 'Valid structured responses only; failures are reported separately, never scored as correct.'}
