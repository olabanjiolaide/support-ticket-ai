"""Run an explicit local-model development pilot; never reads protected test splits."""
import argparse
import hashlib
import json
from time import perf_counter
from pathlib import Path
from .proposals import OllamaProposer, ProposalFailure, align_plan
from .proposal_metrics import compare, summarize
from .version import __version__
from .resources import data_path



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=8)
    args=parser.parse_args()
    if not 1 <= args.limit <= 8: parser.error('Use a limit from 1 to 8.')
    proposer=OllamaProposer(args.model)
    status=proposer.status()
    if not status['available']:
        print('Local proposal model is unavailable. No evaluation was performed.')
        return 1
    fixture_bytes=data_path('needs_proposals_development.json').read_bytes()
    fixture=json.loads(fixture_bytes)
    rows=[]
    for case in fixture['cases'][:args.limit]:
        expected=align_plan(case['text'],case['expected_plan'])
        started=perf_counter()
        try:
            result=proposer.propose(case['text'])
            rows.append({'id':case['id'],'valid_structured_response':True,'metrics':compare(expected,result['review']), 'proposal':result,'elapsed_seconds':perf_counter()-started})
        except ProposalFailure as error:
            rows.append({'id':case['id'],'valid_structured_response':False,'failure_code':error.code,'metrics':None,'elapsed_seconds':perf_counter()-started})
        print(f"Completed {len(rows)}/{min(args.limit,len(fixture['cases']))}",flush=True)
    report={'live_model_evaluated':True,'evaluation_scope':'Authored development cases only; no independent generalization claim.',
            'manual_review_pilot_used':False,'locked_test_used':False,'model':status['model'],
            'application_version':__version__,'model_digest':status.get('model_digest'),
            'fixture_sha256':hashlib.sha256(fixture_bytes).hexdigest(),'metric_version':2,'matching_rule':'One-to-one active evidence character IoU >= 0.5; category and kind errors checked after matching.',
            'metric_limitations':'Evidence overlap is a proxy, not proof of semantic equivalence. Clarification wording and relationship evidence correctness require inspection.',
            'summary':summarize(rows),'attempted':len(rows),'valid_structured_responses':sum(row['valid_structured_response'] for row in rows),'cases':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('Saved development pilot. Valid evidence does not establish correct meaning.')
    return 0


if __name__=='__main__':raise SystemExit(main())
