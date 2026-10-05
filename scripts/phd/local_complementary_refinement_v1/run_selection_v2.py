"""Explicit selection of successful same-policy attempts; never move failed runs."""
import hashlib
import json
from pathlib import Path
import re


def require(ok, why):
    if not ok:
        raise ValueError(why)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def safe_run(task, region, condition, relative):
    require(re.fullmatch(r'P[123]', region) and re.fullmatch(r'LC_D(005|0005|0)_P(native|release)', condition), 'Unknown run identity')
    default = f'runs/{region}/{condition}'
    retry = re.fullmatch(re.escape(f'retries/{region}_{condition}_attempt')+r'(?:[2-9]|[1-9][0-9]+)', relative)
    require(relative == default or retry is not None, 'Unsafe or differently identified run path')
    root = Path(task).resolve(); candidate = root/relative
    require(candidate.resolve() == candidate and candidate.is_relative_to(root), 'Run path must not alias or escape task')
    return candidate


def receipt_identity(r, cfg, region, condition, phase, config_sha, binding_sha, status='PASS'):
    expected = dict(status=status, region=region, condition=condition, phase=phase,
                    task_id=cfg['task_id'], scientific_verdict=None, runtime_image_id=cfg['runtime']['image_id'])
    require(all(r.get(k) == v for k,v in expected.items()), 'Attempt receipt identity/status differs')
    require(r.get('config_sha256', r.get('config',{}).get('sha256')) == config_sha and
            r.get('input_binding',{}).get('sha256') == binding_sha, 'Attempt config/binding differs')


def load_selection(path, task, cfg, config_sha, binding_sha, bind):
    """Require all18 identities and hash-verified PASS phases, including retry history."""
    path = Path(path)
    require(path.resolve().is_relative_to(Path(task).resolve()), 'Selection manifest outside new task')
    bind(path); selection = read(path)
    require(selection.get('schema') == 'jbgs.local_run_selection.v2' and selection.get('scientific_verdict') is None,
            'Selection schema/verdict differs')
    require(selection.get('task_id') == cfg['task_id'] and selection.get('config_sha256') == config_sha and
            selection.get('input_binding_sha256') == binding_sha, 'Selection contract differs')
    require(selection.get('selection_uses_quality_metrics') is False, 'Outcome-based selection forbidden')
    records = selection['runs']; expected = {(r,c['id']) for r in cfg['regions'] for c in cfg['conditions']}
    keys = [(r['region'],r['condition']) for r in records]
    require(len(keys) == len(set(keys)) == len(expected) == 18 and set(keys) == expected, 'Selection must contain exactly full18')
    result = {}
    for record in records:
        region, condition = record['region'], record['condition']
        run = safe_run(task, region, condition, record['relative_path'])
        receipts = {}
        require(set(record['phase_receipt_sha256']) == {'train','render','metrics'}, 'All phase hashes required')
        for phase in ['train','render','metrics']:
            p = run/(phase+'_receipt.json');bind(p, record['phase_receipt_sha256'][phase]); r = read(p)
            receipt_identity(r,cfg,region,condition,phase,config_sha,binding_sha);receipts[phase]=r
        failures = record.get('failed_attempts', [])
        retry = record['relative_path'].startswith('retries/')
        require(bool(failures) == retry, 'Retry must retain failed history; original successful run has no retry history')
        if retry:
            require(record.get('reason') == 'FIRST_SUCCESSFUL_SAME_POLICY_RETRY_AFTER_CUDA_OOM', 'Retry reason differs')
            number = int(record['relative_path'].rsplit('attempt',1)[1])
            history = [f'runs/{region}/{condition}'] + [f'retries/{region}_{condition}_attempt{i}' for i in range(2,number)]
            require([x['relative_path'] for x in failures] == history, 'Every preceding attempt must be retained in order')
        seen = set()
        for previous in failures:
            old = safe_run(task,region,condition,previous['relative_path'])
            require(old != run and str(old) not in seen, 'Duplicate/self failed history');seen.add(str(old))
            p=old/'train_receipt.json';bind(p,previous['train_receipt_sha256']);r=read(p)
            receipt_identity(r,cfg,region,condition,'train',config_sha,binding_sha,'FAIL')
            bind(old/'train.log',previous['train_log_sha256'])
            require('torch.cuda.OutOfMemoryError' in (old/'train.log').read_text(errors='replace'), 'Declared CUDA OOM absent')
            for key in ['command','environment','anchor','source_provenance','driver','training_start_iteration','training_end_iteration']:
                require(r.get(key) == receipts['train'].get(key), 'Retry changed frozen training policy: '+key)
        result[region,condition]=run
    return result


def run_from_evaluation(task, region, condition, evaluation, bind):
    """Use the source fixed by this evaluation receipt, independent of later selections."""
    sources = evaluation.get('selected_run_sources')
    if sources is None:
        return safe_run(task,region,condition,f'runs/{region}/{condition}')
    selected = [r for r in sources if (r['region'],r['condition']) == (region,condition)]
    require(len(selected) == 1, 'Evaluation run source is absent or duplicated')
    row=selected[0];run=safe_run(task,region,condition,row['relative_path'])
    require(set(row['phase_receipt_sha256']) == {'train','render','metrics'}, 'Evaluation phase hashes incomplete')
    for phase in ['train','render','metrics']:
        p=run/(phase+'_receipt.json');bind(p,row['phase_receipt_sha256'][phase]);r=read(p)
        require(r.get('status')=='PASS' and r.get('region')==region and r.get('condition')==condition and
                r.get('phase')==phase and r.get('scientific_verdict') is None,'Evaluated run phase differs')
    return run


def make_selection(task, cfg, config_sha, binding_sha, overrides):
    """Only phase completion selects attempts; no model quality is read."""
    expected = {(r,c['id']) for r in cfg['regions'] for c in cfg['conditions']}
    require(set(overrides) <= expected, 'Unknown retry override')
    rows=[]
    for region,condition in sorted(expected):
        relative=overrides.get((region,condition),f'runs/{region}/{condition}')
        run=safe_run(task,region,condition,relative)
        history=[]
        if relative.startswith('retries/'):
            number=int(relative.rsplit('attempt',1)[1])
            previous=[f'runs/{region}/{condition}']+[f'retries/{region}_{condition}_attempt{i}' for i in range(2,number)]
            for name in previous:
                old=safe_run(task,region,condition,name)
                history.append(dict(relative_path=name,train_receipt_sha256=digest(old/'train_receipt.json'),
                                    train_log_sha256=digest(old/'train.log')))
        rows.append(dict(region=region,condition=condition,relative_path=relative,
            phase_receipt_sha256={p:digest(run/(p+'_receipt.json')) for p in ['train','render','metrics']},
            failed_attempts=history,reason='FIRST_SUCCESSFUL_SAME_POLICY_RETRY_AFTER_CUDA_OOM' if history else 'ORIGINAL_SUCCESSFUL_ATTEMPT'))
    return dict(schema='jbgs.local_run_selection.v2',task_id=cfg['task_id'],scientific_verdict=None,
                config_sha256=config_sha,input_binding_sha256=binding_sha,selection_uses_quality_metrics=False,runs=rows)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['build','export'])
    parser.add_argument('--task',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--binding',type=Path,required=True)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--retry',action='append',default=[],help='REGION/CONDITION=relative retry path')
    args=parser.parse_args();cfg=read(args.config)
    def bind(path, expected=None):
        actual=digest(path)
        require(expected is None or actual==expected,'Bound source hash differs')
        return actual
    overrides={}
    for entry in args.retry:
        key,value=entry.split('=',1);identity=tuple(key.split('/'))
        require(identity not in overrides,'Duplicate retry override');overrides[identity]=value
    if args.operation=='build':
        require(not args.selection.exists(),'Selection manifest is immutable')
        require(args.selection.resolve().is_relative_to(args.task.resolve()),'Selection outside task')
        selection=make_selection(args.task,cfg,digest(args.config),digest(args.binding),overrides)
        # Validate before publishing the one immutable selection file.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='selection_validation_',dir=args.task) as temporary:
            staging=Path(temporary)/'selection.json';staging.write_text(json.dumps(selection,indent=2)+'\n')
            load_selection(staging,args.task,cfg,digest(args.config),digest(args.binding),bind)
            with args.selection.open('x') as stream:stream.write(staging.read_text())
    else:
        require(not overrides,'Export does not accept retry overrides')
    selected=load_selection(args.selection,args.task,cfg,digest(args.config),digest(args.binding),bind)
    for (region,condition),path in sorted(selected.items()):
        print(region,condition,path.relative_to(args.task),sep='\t')


if __name__=='__main__':
    main()
