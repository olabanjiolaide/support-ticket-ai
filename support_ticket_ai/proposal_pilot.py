"""Run an explicit local-model development pilot; never reads protected test splits."""
import argparse
import hashlib
import json
from time import perf_counter
from pathlib import Path
from .proposals import OllamaProposer, ProposalFailure, align_plan, PROMPT_VERSION
from .proposal_metrics import compare, summarize
from .version import __version__
from .resources import data_path



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interpretation-mode', choices=['single','staged'], default='single')
    parser.add_argument('--grouping-contract',choices=['full','memberships','constrained','anchored'],default='full')
    parser.add_argument('--role-prompt',choices=['baseline','focused'],default='baseline',help='First-pass role definitions for staged mode only.')
    parser.add_argument('--model',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int)
    parser.add_argument('--evidence-mode',choices=['fragments','excerpts'],default='fragments')
    parser.add_argument('--fragment-prompt-version', type=int, choices=[3, 4], default=PROMPT_VERSION,
                        help='Compare interpretation prompts on the same numbered evidence; fragments mode only.')
    parser.add_argument('--suite',choices=['development','evidence-regressions','role-contrasts'],default='development')
    args=parser.parse_args()
    if args.grouping_contract != 'full' and args.interpretation_mode != 'staged':
        parser.error('Membership grouping requires staged interpretation mode.')
    if args.role_prompt != 'baseline' and args.interpretation_mode != 'staged':
        parser.error('--role-prompt focused requires staged interpretation mode.')
    if args.output.exists(): parser.error('Output already exists; choose another filename.')
    if args.evidence_mode != 'fragments' and args.fragment_prompt_version != PROMPT_VERSION:
        parser.error('--fragment-prompt-version applies only to fragments evidence mode.')
    if args.interpretation_mode == 'staged' and (args.evidence_mode != 'fragments' or args.fragment_prompt_version != 4):
        parser.error('Staged comparison requires fragments and baseline prompt version 4.')
    fixture_name = {'development':'needs_proposals_development.json','evidence-regressions':'needs_evidence_regressions.json','role-contrasts':'needs_role_contrasts.json'}[args.suite]
    fixture_bytes=data_path(fixture_name).read_bytes()
    fixture=json.loads(fixture_bytes)
    if args.limit is None: args.limit=len(fixture['cases'])
    if not 1 <= args.limit <= len(fixture['cases']): parser.error('Limit must be within the selected development suite.')
    proposer=OllamaProposer(args.model,evidence_mode=args.evidence_mode, fragment_prompt_version=args.fragment_prompt_version)
    if args.interpretation_mode == 'staged':
        from .staged_proposals import StagedProposer
        if args.grouping_contract == 'anchored':
            from .anchored_grouping import AnchoredStagedProposer
            proposer = AnchoredStagedProposer(args.model,role_prompt=args.role_prompt)
        elif args.grouping_contract == 'constrained':
            from .constrained_grouping import ConstrainedStagedProposer
            proposer = ConstrainedStagedProposer(args.model,role_prompt=args.role_prompt)
        elif args.grouping_contract == 'memberships':
            from .compact_grouping import CompactStagedProposer
            proposer = CompactStagedProposer(args.model,role_prompt=args.role_prompt)
        else:
            proposer = StagedProposer(args.model,role_prompt=args.role_prompt)
    status=proposer.status()
    if not status['available']:
        print('Local proposal model is unavailable. No evaluation was performed.')
        return 1
    rows=[]
    for case in fixture['cases'][:args.limit]:
        expected=align_plan(case['text'],case['expected_plan'])
        started=perf_counter()
        try:
            result=proposer.propose(case['text'])
            rows.append({'id':case['id'],'valid_structured_response':True,'metrics':compare(expected,result['review']), 'proposal':result,'elapsed_seconds':perf_counter()-started})
        except ProposalFailure as error:
            rows.append({'id':case['id'],'valid_structured_response':False,'failure_code':error.code,'validation_code':error.validation_code,'generation_attempts':error.attempts,'diagnostics':getattr(error,'diagnostics',None),'metrics':None,'elapsed_seconds':perf_counter()-started})
        print(f"Completed {len(rows)}/{min(args.limit,len(fixture['cases']))}",flush=True)
    report={'live_model_evaluated':True,'evaluation_scope':'Authored development cases only; no independent generalization claim.',
            'manual_review_pilot_used':False,'locked_test_used':False,'model':status['model'],
            'application_version':__version__,'model_digest':status.get('model_digest'),
            'grouping_contract':args.grouping_contract if args.interpretation_mode == 'staged' else None,'role_prompt':args.role_prompt if args.interpretation_mode == 'staged' else None,'interpretation_mode':args.interpretation_mode,'evidence_mode':args.evidence_mode,'suite':args.suite,'prompt_version':proposer.prompt_version,
            'fixture_sha256':hashlib.sha256(fixture_bytes).hexdigest(),'metric_version':3,'matching_rule':'One-to-one active evidence character IoU >= 0.5; category and kind errors checked after matching.',
            'metric_limitations':'Evidence overlap is a proxy, not proof of semantic equivalence. Clarification presence is compared with authored expectations only; wording, usefulness and relationship evidence correctness require human inspection.',
            'summary':summarize(rows),'attempted':len(rows),'valid_structured_responses':sum(row['valid_structured_response'] for row in rows),'cases':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as output:
        output.write(json.dumps(report,indent=2)+'\n')
    print('Saved development pilot. Valid evidence does not establish correct meaning.')
    return 0


if __name__=='__main__':raise SystemExit(main())
