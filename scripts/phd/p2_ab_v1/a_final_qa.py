"""Independent completed-result QA. Writes only its own new receipt directory."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import cv2
import numpy as np

REPO=Path(__file__).resolve().parents[3]


def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def write(p,data):Path(p).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def stamp():return datetime.now(timezone.utc).isoformat()
def near(a,b):
    if a is None or b is None:assert a is b,(a,b)
    else:np.testing.assert_allclose(a,b,atol=1e-10,rtol=1e-9)


def main(config):
    cfg=read(config);out=Path(cfg['output']);base=Path(cfg['artifact_parent']);started=time.monotonic()
    if not out.is_dir() or any(out.iterdir()):raise ValueError('new empty output required')
    sources=[Path(__file__),config,REPO/'src/phd/p2_ab_v1/decision.py',REPO/'src/phd/p2_ab_v1/reconstruction.py',
        REPO/'src/phd/p2_ab_v1/evaluation.py']
    sources+=list((REPO/'scripts/phd/p2_ab_v1').glob('c_*.py'))
    sources+=list((REPO/'tests/phd').glob('test_p2_ab*.py'))
    sources+=[REPO/'scripts/repository/validate_agent_instructions.py',REPO/'tests/repository/test_agent_instruction_sync.py']
    source_hashes={str(p.relative_to(REPO)):sha(p) for p in sources}
    for p in sources:
        dest=out/'source_snapshot'/p.relative_to(REPO);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    write(out/'PRE_QA.json',dict(started_utc=stamp(),config=cfg,source_sha256=source_hashes,scientific_verdict=None))
    report=dict(task_id=cfg['task_id'],scientific_verdict=None,scope=cfg['scope'],checks={})
    try:
        commands=[('new_workstream_tests',[sys.executable,'-m','unittest','discover','-s','tests/phd','-p','test_p2_ab*.py','-v']),
            ('agent_instruction_validator',[sys.executable,'scripts/repository/validate_agent_instructions.py']),
            ('agent_instruction_tests',[sys.executable,'-m','unittest','tests.repository.test_agent_instruction_sync','-v']),
            ('previous_workspace_hashes',['sha256sum','--check',str(base/cfg['preservation_inventory'])])]
        command_results=[]
        for name,cmd in commands:
            result=subprocess.run(cmd,cwd=REPO,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
            (out/(name+'.log')).write_text(result.stdout)
            command_results.append(dict(name=name,command=cmd,returncode=result.returncode,log=name+'.log'))
            assert result.returncode==0,(name,result.stdout[-3000:])
        report['checks']['commands']=command_results
        a=base/cfg['a_run'];c=base/cfg['integrated_run'];app=base/cfg['appearance_run'];summ=base/cfg['summary_run']
        common=base/cfg['common_run']/'common';ref=base/cfg['common_run']/'evaluation_v2'
        paths=[a/'decision_rows.jsonl',c/'joined_decision_units.jsonl',c/'decision_risk_coverage.json',
            c/'reconstruction_unit_metrics.json',app/'common_appearance.json',app/'PRE_EVALUATION_DOMAIN.json',
            summ/'reconstruction_summary.json',common/'units.json',ref/'evaluation_reference.npz']
        inputs={str(p):sha(p) for p in paths}
        groups=defaultdict(list);n=0
        with (a/'decision_rows.jsonl').open() as sa,(c/'joined_decision_units.jsonl').open() as sc:
            for ar,cr in zip(sa,sc,strict=True):
                x,y=json.loads(ar),json.loads(cr);n+=1
                for k in ('unit_id','unit_index','condition','method','threshold','tolerance_m','action','strict_current_use_action'):
                    assert x[k]==y[k],(k,x[k],y[k])
                assert y['strict_current_use_action']=='ABSTAIN'
                assert set(x['candidate_states'])==set(y['candidate_evaluation'])
                labels={}
                for s,state in x['candidate_states'].items():
                    z=y['candidate_evaluation'][s]
                    assert state['candidate_index']==z['candidate_index'];near(state['offset_z_m'],z['offset_z_m'])
                    expected=bool(z['p90_m']<=y['tolerance_m']) if z['reference_supported'] and z['p90_m'] is not None else None
                    assert z['conditional_candidate_ok'] is expected
                    labels[s]=expected
                groups[(y['condition'],y['threshold'],y['tolerance_m'],y['method'])].append((y['unit_id'],y['action'],labels))
        risk=read(c/'decision_risk_coverage.json')
        for row in risk:
            g=groups[row['condition'],row['threshold'],row['tolerance_m'],row['method']]
            assert len(g)==64==len({x[0] for x in g})
            accepted=[(a,l) for _,a,l in g if a!='ABSTAIN'];ev=[(a,l) for a,l in accepted if l.get(a) is not None]
            bad=sum(l[a] is False for a,l in ev);usable=sum(any(v is True for v in l.values()) for _,_,l in g)
            abstainusable=sum(a=='ABSTAIN' and any(v is True for v in l.values()) for _,a,l in g)
            for k,value in dict(total_units=64,accepted_units=len(accepted),evaluated_accepted_units=len(ev),
                false_accept_units=bad,accepted_evaluation_unknown_units=len(accepted)-len(ev),
                abstained_units=64-len(accepted),known_usable_units=usable,abstained_known_usable_units=abstainusable).items():
                assert row[k]==value,(k,row[k],value)
            near(row['coverage'],len(accepted)/64)
            near(row['false_accept_rate_evaluated'],bad/len(ev) if ev else None)
            near(row['usable_abstention_rate'],abstainusable/usable if usable else None)
        report['checks']['A_C_join_and_independent_risk']=dict(rows=n,settings=len(risk),fixed_units=64,status='PASS')
        pilot=read(common/'units.json')['pilot_unit_indices'];rp=np.load(ref/'evaluation_reference.npz',allow_pickle=False)
        expected_ref=sum(int((rp['uas_unit_index']==ui).sum()) for ui in pilot)
        bmetrics=read(c/'reconstruction_unit_metrics.json');summary=read(summ/'reconstruction_summary.json')
        for bm in bmetrics:
            assert len(bm['units'])==64 and {u['unit_index'] for u in bm['units']}==set(pilot)
            for u in bm['units']:
                assert u['reference_count']==int((rp['uas_unit_index']==u['unit_index']).sum())
                for s in u['tolerance_sweep']:
                    assert s['reference_recovered_count']+s['missing_reference_point_count']==u['reference_count']
                    near(s['reference_recall'],s['reference_recovered_count']/u['reference_count'] if u['reference_count'] else None)
                    if not u['prediction_count']:
                        assert s['reference_recovered_count']==0 and s['prediction_precision'] is None
            sr=next(s for s in summary if s['run']==bm['run'] and s.get('arm')==bm.get('arm'))
            emitted=sum(u['prediction_count']>0 for u in bm['units']);pred=sum(u['prediction_count'] for u in bm['units'])
            rec=sum(next(t['reference_recovered_count'] for t in u['tolerance_sweep'] if t['tolerance_m']==.5) for u in bm['units'])
            good=sum(next(t['predicted_inlier_count'] for t in u['tolerance_sweep'] if t['tolerance_m']==.5) for u in bm['units'])
            assert sr['emitted_units']==emitted and sr['missing_units']==64-emitted
            assert sr['reference_native_points']==expected_ref and sr['emitted_surface_sample_points']==pred
            near(sr['reference_recall_050m'],rec/expected_ref)
            near(sr['prediction_precision_050m'],good/pred if pred else None)
        report['checks']['B_geometry_denominators_and_summary']=dict(arms=len(bmetrics),reference_native_points=expected_ref,status='PASS')
        appearance=read(app/'common_appearance.json');domains=read(app/'PRE_EVALUATION_DOMAIN.json')['views'];raw_count=0
        fixed_image=base/'PHD-P2-AB-B-IMAGE-v1'/'surface_texturing';fixed_prior=base/'PHD-P2-AB-B-PRIOR-v2'/'surface_texturing'
        for d in domains:
            iid=d['image_id'];mask=np.load(app/f'domain_mask_{iid}.npy',allow_pickle=False)
            im=np.load(fixed_image/f'render_{iid}.npz',allow_pickle=False)['alpha'].squeeze()
            pr=np.load(fixed_prior/f'render_{iid}.npz',allow_pickle=False)['alpha'].squeeze()
            assert np.array_equal(mask,(im>=.5)|(pr>=.5))
            assert int(mask.sum())==d['pixels'];raw_count+=d['pixels']
        for row in appearance:
            if row['arm']=='no_geometry':
                assert row['input_domain_pixels']==raw_count and row['covered_pixels']==0
                assert row['ray_coverage']==0 and row['mae'] is None and row['psnr_db'] is None
                assert row['per_view']==[]
                sr=next(s for s in summary if s['run']==row['run'] and s['arm']=='no_geometry')
                assert sr['reference_recall_050m']==0 and sr['common_ray_coverage']==0
                assert sr['common_ray_psnr_db'] is None and sr['emitted_units']==0 and sr['missing_units']==64
                continue
            sse=0.;ab=0.;n=0;cover=0
            folder=base/row['run']/row['arm']
            for d in domains:
                iid=d['image_id'];mask=np.load(app/f'domain_mask_{iid}.npy',allow_pickle=False)
                p=folder/f'render_{iid}.npz';target=folder/f'target_{iid}.png'
                assert sha(target)==d['target_sha256']
                payload=np.load(p,allow_pickle=False);t=cv2.cvtColor(cv2.imread(str(target)),cv2.COLOR_BGR2RGB)/255.
                error=payload['rgb'][mask].astype(float)-t[mask]
                sse+=float(np.square(error).sum());ab+=float(abs(error).sum());n+=int(mask.sum())
                cover+=int((mask&(payload['alpha'].squeeze()>=.5)).sum())
                inputs[str(p)]=sha(p);inputs[str(target)]=sha(target)
            assert row['input_domain_pixels']==n==raw_count and row['covered_pixels']==cover
            near(row['mae'],ab/(3*n));near(row['psnr_db'],-10*np.log10(max(sse/(3*n),1e-12)))
            near(row['ray_coverage'],cover/n)
            sr=next(s for s in summary if s['run']==row['run'] and s['arm']==row['arm'])
            near(sr['common_ray_psnr_db'],row['psnr_db']);near(sr['common_ray_coverage'],row['ray_coverage'])
        report['checks']['RGB_array_independent_recompute']=dict(arms=len(appearance),views=len(domains),fixed_rays=raw_count,status='PASS')
        assert all(sha(p)==h for p,h in inputs.items())
        report['source_changed_during_qa']=[p for p,h in source_hashes.items() if sha(REPO/p)!=h]
        assert not report['source_changed_during_qa']
        report.update(status='PASS_COMPLETED_RESULTS',input_sha256=inputs,completed_utc=stamp(),elapsed_seconds=time.monotonic()-started,
            caveats=['current absolute geometry remains uncalibrated numeric-frame diagnostic',
                'same historical development observations and upstream MVS lineage; not confirmatory independence',
                'summary error means only on emitted units require completeness denominator alongside',
                'entire ABSTAIN branch has geometry recovery zero; if represented in appearance its RGB metrics must be null',
                cfg['scope']])
        write(out/'QA_RECEIPT.json',report)
        print(json.dumps({k:v for k,v in report.items() if k not in ('input_sha256','checks')}),flush=True)
    except Exception as exc:
        report.update(status='FAILED',error=repr(exc),traceback=traceback.format_exc(),elapsed_seconds=time.monotonic()-started)
        write(out/'QA_FAILED.json',report);raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);main(p.parse_args().config.resolve())
