"""Docker-only receipt selection for unattended analysis; never read quality to select runs."""
import argparse,hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def require(ok,why):
    if not ok:raise ValueError(why)
def input_hashes(r):return {x['sha256'] for x in r.get('inputs',[]) if isinstance(x,dict) and 'sha256' in x}
def derivative(task,kind,evaluation):
    digest=sha(evaluation/'receipt.json');matches=[]
    for p in (task/kind).glob('attempt_*/receipt.json'):
        r=read(p)
        if digest in input_hashes(r):matches.append(p.parent)
    require(bool(matches),'No analysis receipt binds evaluation: '+kind)
    return sorted(matches)[-1]
def current_sources(task):
    current=read(task/'review_site/current.json')['packet']
    return read(task/'review_site'/current/'sources.json')
def desired_regions(task):
    current=read(task/'review_site/current.json')['packet'];packet=read(task/'review_site'/current/'data.json')
    # Phase PASS is the only trigger. No image/geometry quality controls scheduling.
    finished=set()
    for line in (task/'queue/events.log').read_text().splitlines():
        match=re.search(r'PAIR_FINISHED (P[123]) (005|0005|0) failed=[01]$',line)
        if match:finished.add(tuple(match.groups()))
    for region in ['P1','P2','P3']:
        published={x['condition'] for x in packet['rows'] if x['region']==region};available=set()
        for depth in ['005','0005','0']:
            if (region,depth) not in finished:continue
            for mode in ['native','release']:
                condition=f'LC_D{depth}_P{mode}';root=task/'runs'/region/condition
                if all((root/(p+'_receipt.json')).exists() and read(root/(p+'_receipt.json')).get('status')=='PASS' for p in ['train','render','metrics']):available.add(condition)
        if available-published:print(region)
def retry_plan(task):
    for region in ['P1','P2','P3']:
        for depth in ['005','0005','0']:
            for mode in ['native','release']:
                condition=f'LC_D{depth}_P{mode}';original=task/'runs'/region/condition
                require((original/'train_receipt.json').exists(),'Missing original train receipt')
                r=read(original/'train_receipt.json')
                if r['status']=='PASS':
                    require(all(read(original/(p+'_receipt.json'))['status']=='PASS' for p in ['render','metrics']),'Failed extraction/metrics requires explicit investigation');continue
                require(r['status']=='FAIL' and 'CUDA out of memory' in (original/'train.log').read_text(errors='replace'),'Only known CUDA OOM permits automatic same-policy retry')
                attempt=f'{region}_{condition}_attempt2';retry=task/'retries'/attempt;queue=task/'retry_queue'/attempt
                if (queue/'exit_code.txt').exists():
                    require((queue/'exit_code.txt').read_text().strip()=='0','Same-policy retry failed: '+attempt)
                    require(all(read(retry/(p+'_receipt.json'))['status']=='PASS' for p in ['train','render','metrics']),'Retry incomplete')
                    action='SELECT'
                elif queue.exists():action='WAIT'
                else:
                    require(not retry.exists(),'Unregistered retry output exists');action='RUN'
                print(action,region,condition,attempt,sep='\t')
def publish_sources(task,evaluation,regions,out):
    roots={k:derivative(task,v,evaluation) for k,v in {'summary':'summary','figures':'figures','maps':'maps','figure_qa':'figures_review','map_qa':'maps_review'}.items()}
    policy=current_sources(task);new_regions=set(regions)
    bundles=[]
    for old in policy['bundles']:
        remaining=[r for r in old['regions'] if r not in new_regions]
        if remaining:bundles.append(dict(old,regions=remaining))
    bundles.append(dict(regions=regions,**{k:str(v.relative_to(task)) for k,v in roots.items()}))
    write(out,dict(schema='jbgs.local_review_sources.v2',scientific_verdict=None,bundles=bundles))

def logged_value(log,key):
    values=[]
    for line in log.read_text().splitlines():
        try:value=json.loads(line)
        except ValueError:continue
        if isinstance(value,dict) and key in value:values.append(value[key])
    require(len(values)==1,'Expected one '+key+' in '+str(log))
    return values[0]

def full_completion(task,evaluation,out,batch):
    """Seal only this batch's full18 analysis chain, including non-viewer outputs."""
    task=task.resolve();evaluation=evaluation.resolve();batch=batch.resolve();inputs={}
    require(evaluation.parent==task/'evaluation' and batch.parent==task/'automation_v2','Completion source escaped task')
    def bind(path):
        path=Path(path);digest=sha(path)
        inputs[str(path)]=dict(path=str(path),sha256=digest);return digest
    def receipt(path):
        value=read(path);bind(path)
        require(value.get('scientific_verdict') is None,'Technical receipts require null scientific verdict')
        return value
    def logged_root(stage,kind,prefix=None):
        log=batch/(stage+'.log');bind(log);value=logged_value(log,'output')
        prefix=prefix or '/task/main_v2/'+kind
        require(isinstance(value,str) and re.fullmatch(re.escape(prefix)+r'/attempt_[A-Za-z0-9_]+',value),'Unexpected '+stage+' output')
        root=task/kind/Path(value).name
        require(root.resolve()==root,'Aliased analysis output')
        return root
    def bound_to(value,digest,label):
        require(digest in {x.get('sha256') for x in value.get('inputs',value.get('input_files',[]))},label+' binds different input')
    ev=receipt(evaluation/'receipt.json');ev_sha=sha(evaluation/'receipt.json')
    require(ev['status']=='COMPLETE_DEVELOPMENT_EVALUATION' and ev['run_count']==ev['expected_full_run_count']==18 and not ev['missing'],'Full18 evaluation required')
    selection_path=task/'run_selection_v2.json';selection=receipt(selection_path);selection_sha=sha(selection_path)
    require(ev.get('run_selection',{}).get('sha256')==selection_sha,'Evaluation selection differs')
    expected={(r,c) for r in ['P1','P2','P3'] for c in [f'LC_D{d}_P{m}' for d in ['005','0005','0'] for m in ['native','release']]}
    rows=selection['runs'];keys=[(x['region'],x['condition']) for x in rows]
    require(len(keys)==len(set(keys))==18 and set(keys)==expected,'Full18 selection identities required')
    require(selection.get('selection_uses_quality_metrics') is False,'Quality-based selection forbidden')
    actual=ev['selected_run_sources']
    require(len(actual)==18 and {(x['region'],x['condition']) for x in actual}==expected,'Evaluation membership differs')
    chosen={(x['region'],x['condition']):x for x in rows}
    for row in actual:
        source=chosen[row['region'],row['condition']]
        require(all(row[k]==source[k] for k in ['relative_path','phase_receipt_sha256']),'Evaluation selected phase binding differs')
    roots={k:logged_root(k,kind,prefix) for k,kind,prefix in [
        ('summary','summary','/summary'),('maps','maps',None),('figure_qa','figures_review',None),
        ('map_qa','maps_review',None),('strata','strata_diagnostic',None),('matrix','matrix_figures',None),
        ('photo_cases','photo_case_summary','/out'),('attempt_costs','attempt_costs','/output')]}
    receipts={k:receipt(v/'receipt.json') for k,v in roots.items()}
    sr=receipts['summary'];require(sr['status']=='COMPLETE_18_DEVELOPMENT_SUMMARY' and sr['observed_condition_count']==sr['expected_condition_count']==18,'Full18 summary required');bound_to(sr,ev_sha,'Summary')
    mr=receipts['maps'];require(mr['status']=='PASS_STATIC_MAPS' and mr['case_count']==18,'Full18 maps required');bound_to(mr,ev_sha,'Maps')
    for key,status in [('figure_qa','PASS_NATIVE_PIXEL_PSNR_AND_BAND_QA'),('map_qa','PASS_EXACT_ORIGINAL_DISTANCES_AND_ALL_CELLS')]:
        value=receipts[key];require(value['status']==status and value['run_count']==18 and value['matrix_status']=='FULL18','Full18 '+key+' required');bound_to(value,ev_sha,key)
    bound_to(receipts['map_qa'],sha(roots['maps']/'receipt.json'),'Map QA')
    st=receipts['strata'];require(st['status']=='PASS' and st['matrix_status']=='COMPLETE_MATRIX' and st['producer_completed_run_count']==st['producer_expected_run_count']==18,'Full18 strata required');bound_to(st,ev_sha,'Strata')
    matrix=receipts['matrix'];require(matrix['status']=='PASS_COMPLETE_18_MATRIX_FIGURES' and matrix['observed_condition_count']==matrix['expected_condition_count']==18 and matrix['not_plotted_condition_count']==0,'Full18 matrix required');bound_to(matrix,sha(roots['summary']/'receipt.json'),'Matrix')
    photo=receipts['photo_cases'];require(photo['status']=='PASS_FULL18_CASE_COMPARISON' and photo['run_count']==18 and photo['case_count']==6 and photo['paired_rows']==72,'Full18 photo cases required');bound_to(photo,ev_sha,'Photo cases')
    costs=receipts['attempt_costs'];require(costs['status']=='PASS_FULL18_ATTEMPT_COSTS' and costs['selected_conditions']==costs['selected_training_attempts']==18 and costs['failed_training_attempts']==sum(len(x['failed_attempts']) for x in rows),'Complete selected and failed attempt costs required');bound_to(costs,selection_sha,'Costs')
    trace_log=batch/'trace.log';bind(trace_log)
    matches=re.findall(r'^Trace attempt: (.+)$',trace_log.read_text(),re.M)
    require(len(matches)==1 and re.fullmatch(r'.*/main_v2/trace_monitor/attempt_[A-Za-z0-9_]+',matches[0]),'Expected one trace attempt')
    trace_root=task/'trace_monitor'/Path(matches[0]).name;trace=receipt(trace_root/'runtime_receipt.json')
    require(trace['status']=='PASS' and trace['matrix_status']=='COMPLETE_MATRIX' and trace['analyzer_status_counts']=={'PASS':18} and trace['paired_iterations']==3960,'Full18 complete refinement traces required')
    require(trace.get('run_selection',{}).get('sha256')==selection_sha,'Trace selection differs')
    require(trace['config_sha256']==selection['config_sha256'] and trace['input_binding_sha256']==selection['input_binding_sha256'],'Trace frozen input contract differs')
    publish_log=batch/'publish.log';bind(publish_log);published=logged_value(publish_log,'packet')
    require(isinstance(published,str) and re.fullmatch(r'/site/packets/packet_[A-Za-z0-9_]+',published),'Unexpected published packet')
    packet=read(task/'review_site/current.json');bind(task/'review_site/current.json')
    require(packet['packet']=='packets/'+Path(published).name,'Current packet is not this batch publication')
    packet_root=task/'review_site'/packet['packet'];pr=receipt(packet_root/'receipt.json')
    require(packet['receipt_sha256']==sha(packet_root/'receipt.json') and pr['status']=='PASS_REVIEW_PACKET' and pr['evaluated_conditions']==18,'Full18 hash-bound review packet required')
    # The publisher already validates copied assets against figure/map QA. Bind
    # its source policy here so an unrelated full18 packet cannot satisfy completion.
    sources=read(packet_root/'sources.json');source_sha=bind(packet_root/'sources.json')
    require(any(x['path']=='sources.json' and x['sha256']==source_sha for x in pr['outputs']),'Published source policy hash differs')
    require(len(sources['bundles'])==1 and set(sources['bundles'][0]['regions'])=={'P1','P2','P3'},'Full18 single evaluation bundle required')
    bundle=sources['bundles'][0]
    for key in ['summary','maps','figure_qa','map_qa']:
        require(task/bundle[key]==roots[key],'Published '+key+' differs from batch')
    figure_root=task/bundle['figures'];require(figure_root.resolve().parent==task/'figures','Figure path escaped task')
    figures=receipt(figure_root/'receipt.json');require(figures['status']=='PASS_MATCHED_FIGURES_WRITTEN_REQUIRES_VISUAL_REVIEW' and len(figures['records'])==18,'Full18 figures required');bound_to(figures,ev_sha,'Figures');bound_to(receipts['figure_qa'],sha(figure_root/'receipt.json'),'Figure QA')
    publish_3d_log=batch/'publish_3d.log';bind(publish_3d_log);published_3d=logged_value(publish_3d_log,'packet')
    require(isinstance(published_3d,str) and re.fullmatch(r'/site/packets/packet_[A-Za-z0-9_]+',published_3d),'Unexpected published 3D packet')
    packet_3d=read(task/'review_3d/current.json');bind(task/'review_3d/current.json')
    require(packet_3d['packet']=='packets/'+Path(published_3d).name,'Current 3D packet is not this batch publication')
    root_3d=task/'review_3d'/packet_3d['packet'];r3=receipt(root_3d/'receipt.json')
    require(sha(root_3d/'receipt.json')==packet_3d['receipt_sha256'] and r3['status']=='PASS_3D_EXPORT_BROWSER_REVIEW_REQUIRED' and r3['evaluated_conditions']==18,'Full18 hash-bound 3D packet required')
    require(r3['source_review_packet']==packet['packet'] and r3['source_review_receipt_sha256']==sha(packet_root/'receipt.json'),'3D packet source review differs');bound_to(r3,sha(packet_root/'receipt.json'),'3D packet')
    expected_3d={(region,condition,kind) for region,condition in expected for kind in ['raw','post']}
    keys_3d=[(x['region'],x['condition'],x['kind']) for x in r3['records']]
    require(len(keys_3d)==len(set(keys_3d))==36 and set(keys_3d)==expected_3d,'All36 unique 3D exports required')
    manifest_3d=read(root_3d/'manifest.json');manifest_sha=bind(root_3d/'manifest.json')
    require(any(x['path']=='manifest.json' and x['sha256']==manifest_sha for x in r3['outputs']),'3D manifest hash differs')
    require(manifest_3d['evaluated_conditions']==18 and manifest_3d['source_review_receipt_sha256']==sha(packet_root/'receipt.json') and manifest_3d['source_review_packet']==packet['packet'],'3D manifest source binding differs')
    browser_log=batch/'browser_3d_qa.log';bind(browser_log)
    browser_paths=re.findall(r'^(.*/main_v2/review_3d/browser_qa/attempt_[A-Za-z0-9_]+/receipt.json)$',browser_log.read_text(),re.M)
    require(len(browser_paths)==1,'Expected exact browser 3D QA receipt')
    browser_root=task/'review_3d/browser_qa'/Path(browser_paths[0]).parent.name;browser=receipt(browser_root/'receipt.json')
    require(browser['status']=='PASS_ACTUAL_3D_MATCHED_CONDITIONS_RAW_POST' and browser['evaluated_conditions']==18,'Full18 actual 3D browser QA required')
    require(browser['manifest_sha256']==manifest_sha and browser['export_receipt_sha256']==sha(root_3d/'receipt.json') and browser['source_review_receipt_sha256']==sha(packet_root/'receipt.json') and browser['source_review_packet']==packet['packet'],'3D browser QA binds different packet')
    require(browser['checks'] and all(x['pass'] is True for x in browser['checks']),'3D browser QA contains failed checks')
    for name in ['Matched G follows LC coefficient and protection','LC actual selected candidate','Six cameras synchronized']:
        details=[x['detail'] for x in browser['checks'] if x['name']==name]
        keys=[(x['region'],x['condition'],x['surface']) for x in details]
        require(len(keys)==len(set(keys))==36 and set(keys)==expected_3d,'3D browser QA misses condition/surface checks: '+name)
    write(out,dict(status='PASS_UNATTENDED_FULL18_ANALYSIS',scientific_verdict=None,finished_at=datetime.now(timezone.utc).isoformat(),
        evaluation=dict(path=str(evaluation),sha256=ev_sha),run_selection_sha256=selection_sha,review_packet=packet,review_3d_packet=packet_3d,inputs=list(inputs.values()),
        manual_interpretation_of_new_figures='PENDING_HUMAN_REVIEW',browser_review_of_new_3d_data='PASS_ACTUAL_3D_MATCHED_CONDITIONS_RAW_POST',
        scope='Full18 technical evaluation, source QA, strata, traces, costs, fixed cases and source-bound 3D export; no scientific verdict'))
def main():
    p=argparse.ArgumentParser();p.add_argument('--task',type=Path,required=True)
    sub=p.add_subparsers(dest='op',required=True)
    sub.add_parser('pending');sub.add_parser('retries')
    x=sub.add_parser('extract');x.add_argument('log',type=Path);x.add_argument('key')
    x=sub.add_parser('resolve');x.add_argument('kind');x.add_argument('evaluation',type=Path)
    x=sub.add_parser('sources');x.add_argument('evaluation',type=Path);x.add_argument('regions');x.add_argument('output',type=Path)
    x=sub.add_parser('complete');x.add_argument('evaluation',type=Path);x.add_argument('output',type=Path);x.add_argument('--batch',type=Path,required=True)
    a=p.parse_args();require(Path('/.dockerenv').exists(),'Docker required')
    if a.op=='pending':desired_regions(a.task)
    elif a.op=='retries':retry_plan(a.task)
    elif a.op=='extract':
        values=[]
        for line in a.log.read_text().splitlines():
            try:r=json.loads(line)
            except ValueError:continue
            if isinstance(r,dict) and a.key in r:values.append(r[a.key])
        require(len(values)==1,'Expected exactly one JSON output path');value=values[0]
        if a.key=='receipt':value=str(Path(value).parent)
        if value.startswith('/summary/'):value='/task/main_v2'+value
        require(re.fullmatch(r'/task/main_v2/[a-z_]+/attempt_[A-Za-z0-9_]+',value),'Unsafe analysis output path');print(value)
    elif a.op=='resolve':print(derivative(a.task,a.kind,a.evaluation))
    elif a.op=='sources':publish_sources(a.task,a.evaluation,a.regions.split(','),a.output)
    else:full_completion(a.task,a.evaluation,a.output,a.batch)
if __name__=='__main__':main()
