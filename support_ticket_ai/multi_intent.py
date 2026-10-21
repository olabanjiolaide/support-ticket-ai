"""Bounded, experimental rules for explicit requests with different routing categories.

This is an experimental guard baseline, not a trained general ambiguity detector.
"""

import re

from .predict import MAX_TEXT_LENGTH

VERSION = 1
MAX_SEGMENTS = 4
BOUNDARY = re.compile(r'(?:\s*,?\s+\band(?:\s+also)?\b\s+|\s+\bplus\b\s+|[;\n]+|[.!?]\s+)', re.I)
ALTERNATIVE = re.compile(r'\b(?:or|either|if|unless|instead|rather\s+than|not\s+only)\b', re.I)
NEGATED = re.compile(r"\b(?:not|never|cannot|can't|don't|doesn't|won't|no\s+longer)\b", re.I)
ACTION = r'(?:send|resend|provide|email|cancel|refund|update|change|remove|delete|stop|unsubscribe|subscribe|reset|recover|track|check|find|issue|create|download|add|correct|explain|show)'
REQUEST = re.compile(
    r'^(?:also\s*,?\s*)?(?:(?:please|kindly)\s+)?(?:'
    r'(?:i|we)\s+(?:also\s+)?(?:want|need|would\s+(?:also\s+)?like)\b|'
    r'(?:can|could|would|will)\s+you\b|'
    + ACTION + r'\b)', re.I)


def inspect_requests(text: str, predict_clause) -> dict:
    """Only flag two accepted affirmative request fragments in different categories.

    At most four additional model calls. No match is not proof of a single intent.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f'Use a nonempty request of at most {MAX_TEXT_LENGTH} characters.')
    text = text.strip().replace('\u2019', "'")
    if ALTERNATIVE.search(text):
        return {'review_triggered': False, 'status': 'conditional_or_alternative_skipped', 'fragments': []}
    parts = [part.strip(' ,.!?\t') for part in BOUNDARY.split(text) if part.strip(' ,.!?\t')]
    if len(parts) > MAX_SEGMENTS:
        return {'review_triggered': False, 'status': 'too_many_segments_skipped', 'fragments': []}
    requests = []
    for part in parts:
        expanded = re.sub(r"\bi'd\b", 'I would', part, flags=re.I)
        if REQUEST.search(expanded) and not NEGATED.search(expanded) and len(expanded.split()) >= 3:
            requests.append(part)
    if len(requests) < 2:
        return {'review_triggered': False, 'status': 'fewer_than_two_explicit_requests', 'fragments': []}
    fragments = []
    categories = set()
    for request in requests:
        prediction = predict_clause(request)
        accepted = (prediction.get('decision') == 'suggestion' and
                    not prediction.get('input_truncated', False) and
                    isinstance(prediction.get('suggested_category'), str) and
                    bool(prediction['suggested_category']))
        if accepted:
            categories.add(prediction['suggested_category'])
        fragments.append({'text': request, 'accepted': accepted,
                          'suggested_category': prediction.get('suggested_category') if accepted else None,
                          'model_top_category': prediction.get('model_top_category'),
                          'uncalibrated_probability': prediction.get('uncalibrated_probability'),
                          'scope_score': prediction.get('scope_score')})
    # A human-agent preference alongside a specific task is not automatically
    # a second routing intent under this project's annotation contract.
    routing_categories = categories - {'CONTACT'} if len(categories) > 1 else categories
    triggered = len(routing_categories) >= 2
    return {'review_triggered': triggered,
            'status': 'different_accepted_request_categories' if triggered else 'no_cross_category_evidence',
            'accepted_categories': sorted(categories),
            'routing_categories_considered': sorted(routing_categories),
            'fragments': fragments}


def guarded_prediction(text: str, predictor) -> dict:
    """Preserve existing abstentions; the prototype can only withhold more requests."""
    original = predictor.predict(text)
    if original['decision'] == 'abstain':
        inspection = {'review_triggered': False, 'status': 'outer_prediction_already_withheld', 'fragments': []}
    else:
        inspection = inspect_requests(text, predictor.predict)
    guarded = dict(original)
    if inspection['review_triggered']:
        guarded.update(suggested_category=None, decision='abstain', requires_human_review=True,
                       review_reason='Experimental clause check found separate requests in different categories. Review the full message.')
    return {'original': original, 'guarded': guarded, 'inspection': inspection}
