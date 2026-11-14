"""Evaluate the staged classifier alone on the authored evidence regressions."""
import argparse
import hashlib
import json
from pathlib import Path
from time import monotonic, perf_counter
import httpx
from .proposal_evidence import source_fragments
from .staged_proposals import StagedProposer, MeaningPlan, ROLE_SYSTEM
from .proposals import ProposalFailure, align_plan
from .resources import data_path
from .version import __version__

ACTIVE = {'request', 'obstacle', 'conditional', 'alternative', 'unclear'}


def score(expected, predicted):
    """Categories are scored only for authored active fragments, even if demoted."""
    if [p['fragment_id'] for p in expected] != [p['fragment_id'] for p in predicted]:
        raise ValueError('Classification must cover the same ordered fragment IDs.')
    return {'fragments':len(expected),
            'role_errors':sum(e['role'] != a['role'] for e,a in zip(expected,predicted)),
            'expected_active_fragments':sum(e['role'] in ACTIVE for e in expected),
            'active_category_errors':sum(e['role'] in ACTIVE and e['category'] != a['category'] for e,a in zip(expected,predicted)),
            'active_demoted_to_background':sum(e['role'] in ACTIVE and a['role'] not in ACTIVE for e,a in zip(expected,predicted)),
            'excluded_promoted_to_active':sum(e['role'] in {'negated','resolved','context'} and a['role'] in ACTIVE for e,a in zip(expected,predicted))}


def classify(engine, text):
    evidence=source_fragments(text)
    deadline=monotonic()+120
    try:
        with httpx.Client(trust_env=False,timeout=httpx.Timeout(120,connect=3),follow_redirects=False) as client:
            before=engine.digest(client,deadline=deadline)
            result=engine.classify_response(client,{'customer_message':text,'source_fragments':evidence['fragments']},deadline)
            remaining=deadline-monotonic()
            if remaining <= 0: raise httpx.ReadTimeout('Time budget exceeded.')
            client.timeout=httpx.Timeout(min(3,remaining))
            if engine.digest(client,deadline=deadline)!=before:
                raise ProposalFailure('model_changed','Local model changed during classification.',attempts=1)
        return {'classifications':result.model_dump(mode='json')['fragments'],'model_digest':before,'evidence':evidence}
    except ProposalFailure as error:
        error.attempts=1
        raise
    except httpx.TimeoutException as error:
        raise ProposalFailure('timeout','Classification exceeded its time budget.',attempts=1) from error
    except (httpx.HTTPError,ValueError,KeyError,TypeError,AttributeError) as error:
        raise ProposalFailure('invalid_output','Classification transport or response failed.',attempts=1) from error


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Output already exists; choose another filename.')
    raw=data_path('needs_evidence_regressions.json').read_bytes()
    fixture=json.loads(raw)
    engine=StagedProposer(args.model)
    if not engine.status()['available']:
        print('Local model unavailable; no evaluation performed.');return 1
    rows=[]
    for case in fixture['cases']:
        review=align_plan(case['text'],case['expected_plan'])
        # This suite deliberately uses exactly the source adapter's boundaries.
        source=source_fragments(case['text'])['fragments']
        if [(p['start'],p['end']) for p in source] != [(p['start'],p['end']) for p in review['parts']]:
            raise ValueError('Authored and source boundaries differ; cannot score fragment labels.')
        categories={g['id']:g['category'] for g in review['groups']}
        expected=[{'fragment_id':p['id'],'role':p['role'],'category':categories.get(p['group_id']) if p['role'] in ACTIVE else None} for p in review['parts']]
        started=perf_counter()
        row={'id':case['id'],'expected':expected}
        try:
            actual=classify(engine,case['text'])
            row.update(valid_structured_response=True,result=actual,metrics=score(expected,actual['classifications']))
        except ProposalFailure as error:
            row.update(valid_structured_response=False,failure_code=error.code,validation_code=error.validation_code,generation_attempts=error.attempts,metrics=None)
        row['elapsed_seconds']=perf_counter()-started;rows.append(row)
        print(f'Completed {len(rows)}/{len(fixture["cases"])}',flush=True)
    valid=[r for r in rows if r['valid_structured_response']]
    keys=['fragments','role_errors','expected_active_fragments','active_category_errors','active_demoted_to_background','excluded_promoted_to_active']
    report={'application_version':__version__,'model':engine.model,'interpretation_mode':'classification_only',
            'live_model_evaluated':True,'fixture_sha256':hashlib.sha256(raw).hexdigest(),
            'prompt_sha256':hashlib.sha256((ROLE_SYSTEM+json.dumps(MeaningPlan.model_json_schema(),sort_keys=True)).encode()).hexdigest(),
            'limitations':'Reused authored development cases. No grouping, clarification or generalization evaluated. Error totals cover valid responses only; failures remain separate. Background category labels are not scored.',
            'summary':{'attempted':len(rows),'valid':len(valid),'failed':len(rows)-len(valid),'valid_response_totals':{k:sum(r['metrics'][k] for r in valid) for k in keys},'mean_elapsed_seconds_all_attempts':sum(r['elapsed_seconds'] for r in rows)/len(rows)},'cases':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(report,f,indent=2)
    print('Saved classification-only development report.');return 0


if __name__=='__main__':raise SystemExit(main())
