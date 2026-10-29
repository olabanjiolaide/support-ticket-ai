"""Run an explicit local-model development pilot; never reads protected test splits."""
import argparse
import json
from pathlib import Path
from .proposals import OllamaProposer, ProposalFailure, align_plan
from .resources import data_path


def compare(expected, actual):
    def roles(document):
        labels = [None]*len(document['source_text'])
        for part in document['parts']:
            for index in range(part['start'],part['end']): labels[index] = part['role']
        return labels
    e,a = roles(expected),roles(actual)
    indices = [i for i,c in enumerate(expected['source_text']) if not c.isspace()]
    return {'category_set_match':sorted({g['category'] for g in expected['groups']}) == sorted({g['category'] for g in actual['groups']}),
            'need_count_match':len(expected['groups']) == len(actual['groups']),
            'non_whitespace_role_character_agreement':sum(e[i]==a[i] for i in indices)/len(indices),
            'relation_kind_set_match':sorted({r['kind'] for r in expected['relations']}) == sorted({r['kind'] for r in actual['relations']})}


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
    fixture=json.loads(data_path('needs_proposals_development.json').read_text())
    rows=[]
    for case in fixture['cases'][:args.limit]:
        expected=align_plan(case['text'],case['expected_plan'])
        try:
            result=proposer.propose(case['text'])
            rows.append({'id':case['id'],'valid_structured_response':True,'metrics':compare(expected,result['review']), 'proposal':result})
        except ProposalFailure as error:
            rows.append({'id':case['id'],'valid_structured_response':False,'failure_code':error.code,'metrics':None})
        print(f"Completed {len(rows)}/{min(args.limit,len(fixture['cases']))}",flush=True)
    report={'live_model_evaluated':True,'evaluation_scope':'Authored development cases only; no independent generalization claim.',
            'manual_review_pilot_used':False,'locked_test_used':False,'model':status['model'],
            'attempted':len(rows),'valid_structured_responses':sum(row['valid_structured_response'] for row in rows),'cases':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('Saved development pilot. Valid evidence does not establish correct meaning.')
    return 0


if __name__=='__main__':raise SystemExit(main())
