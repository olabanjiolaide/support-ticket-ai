"""Compare clarification prompts alone on messages from a saved combined report."""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter
from .clarification_pilot import evaluate, decision_schema
from .combined_pilot import QUESTION_SYSTEMS
from .proposal_evidence import source_fragments
from .proposals import OllamaProposer, ProposalFailure
from .version import __version__

VARIANTS = ('reused-constrained', 'meaning-focused')


def saved_messages(report):
    if report.get('evaluation_mode') != 'combined_conditions_questions':
        raise ValueError('Input must be a combined-pilot report.')
    cases = report.get('cases')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
        raise ValueError('Expected 1 to 200 saved cases.')
    result = []
    seen = set()
    for case in cases:
        ident = case['id']
        if not isinstance(ident, str) or not ident or ident in seen:
            raise ValueError('Case IDs must be unique nonempty strings.')
        seen.add(ident)
        text = case.get('proposal', {}).get('review', {}).get('source_text')
        if not isinstance(text, str):
            raise ValueError('Every case needs saved source text; use the earlier complete report. No cases are silently skipped.')
        evidence = source_fragments(text)
        result.append({'id': ident, 'source_text': text,
                       'payload_sha256': hashlib.sha256(json.dumps({'customer_message': text,
                           'source_fragments': evidence['fragments']}, ensure_ascii=False).encode()).hexdigest(),
                       'schema_sha256': hashlib.sha256(json.dumps(decision_schema(evidence,'constrained'),sort_keys=True).encode()).hexdigest()})
    return result


def compare_questions(engine, messages, digest):
    rows = []
    for index, message in enumerate(messages):
        order = list(VARIANTS if index % 2 == 0 else reversed(VARIANTS))
        row = {**message, 'variant_order': order, 'variants': {}}
        for variant in order:
            started = perf_counter()
            try:
                result = evaluate(engine, message['source_text'], 'constrained', system=QUESTION_SYSTEMS[variant])
                if result['model_digest'] != digest:
                    raise ProposalFailure('model_changed', 'Model differs from the comparison starting identity.', attempts=1)
                item = {'valid_structured_response': True, 'result': result}
            except ProposalFailure as error:
                item = {'valid_structured_response': False, 'failure_code': error.code,
                        'validation_code': error.validation_code, 'diagnostics': getattr(error,'diagnostics',None)}
            item['elapsed_seconds'] = perf_counter() - started
            row['variants'][variant] = item
        row['both_valid'] = all(item['valid_structured_response'] for item in row['variants'].values())
        rows.append(row)
        print(f'Completed paired case {len(rows)}/{len(messages)}', flush=True)
    return rows


def summarize(rows):
    return {'attempted_pairs': len(rows), 'both_valid_pairs': sum(row['both_valid'] for row in rows),
            'variants': {variant: {'attempted': len(rows),
                'valid': sum(row['variants'][variant]['valid_structured_response'] for row in rows),
                'failed': sum(not row['variants'][variant]['valid_structured_response'] for row in rows)}
                for variant in VARIANTS}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-report', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():parser.error('Output already exists; choose another filename.')
    try:
        if args.input_report.stat().st_size > 10 * 1024 * 1024:raise ValueError('Input report too large.')
        raw = args.input_report.read_bytes()
        messages = saved_messages(json.loads(raw))
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
        parser.error(str(error))
    engine = OllamaProposer(args.model)
    status = engine.status()
    if not status['available']:print('Local model unavailable; no comparison performed.');return 1
    rows = compare_questions(engine, messages, status['model_digest'])
    report = {'application_version': __version__, 'evaluation_mode': 'paired_clarification_only',
        'model': engine.model, 'model_digest': status['model_digest'], 'live_model_evaluated': True,
        'input_report_sha256': hashlib.sha256(raw).hexdigest(),
        'prompt_sha256': {variant: hashlib.sha256(QUESTION_SYSTEMS[variant].encode()).hexdigest() for variant in VARIANTS},
        'limitations': 'Observed authored development messages; no independent accuracy estimate. Same source/schema and model settings for both variants; execution order alternates by case, not a repeated crossover experiment. One generation per variant, no classification/grouping calls, no retry or repair. All failures retained. No gold labels sent or wording quality inferred; inspect raw decisions and questions. Timing is observational.',
        'summary': summarize(rows), 'cases': rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as handle:json.dump(report,handle,indent=2)
    print('Saved paired clarification comparison. Wording still requires review.')
    return 0


if __name__ == '__main__':raise SystemExit(main())
