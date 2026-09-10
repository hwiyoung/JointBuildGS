"""Publish a new immutable local review packet from verified analysis receipts."""
import argparse,csv,hashlib,json,os,shutil
from datetime import datetime,timezone
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def require(ok,why):
    if not ok:raise ValueError(why)
def hashes(value):
    if isinstance(value,dict):
        return {v for k,v in value.items() if k=='sha256' and isinstance(v,str)}.union(*(hashes(v) for v in value.values()))
    if isinstance(value,list):return set().union(*(hashes(v) for v in value))
    return set()

def main():
    p=argparse.ArgumentParser()
    for n in ['task','sources','app','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();require(Path('/.dockerenv').exists(),'Docker required')
    policy=read(a.sources);require(policy['scientific_verdict'] is None,'Technical review only')
    stamp='packet_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out=a.output/'packets'/stamp;out.mkdir(parents=True,exist_ok=False)
    (out/'assets').mkdir();(out/'downloads').mkdir();inputs={};rows=[];methods={};regions_seen=set()
    def bind(path,expected=None):
        h=sha(path);require(expected is None or h==expected,'Source digest differs: '+str(path))
        inputs[str(path)]=dict(path=str(path),sha256=h,bytes=path.stat().st_size);return h
    def safe(relative):
        x=a.task/relative;require(x.resolve().is_relative_to(a.task.resolve()),'Source escaped new task');return x
    def csv_file(root,name,receipt):
        record=next(x for x in receipt['outputs'] if x['path']==name);path=root/name;bind(path,record['sha256'])
        with path.open() as stream:return list(csv.DictReader(stream))
    def copy_bound(root,name,receipt,target):
        record=next(x for x in receipt['outputs'] if x['path']==name);path=root/name;bind(path,record['sha256'])
        shutil.copyfile(path,out/target);return target
    bind(a.sources);bind(Path(__file__))
    for bundle in policy['bundles']:
        receipts={};roots={}
        for kind in ['summary','figures','maps','figure_qa','map_qa']:
            roots[kind]=safe(bundle[kind]);path=roots[kind]/'receipt.json';bind(path);receipts[kind]=read(path)
            require(receipts[kind]['scientific_verdict'] is None,'Scientific verdict forbidden')
        sr,fr,mr=receipts['summary'],receipts['figures'],receipts['maps']
        require(sr['status'] in ['COMPLETE_18_DEVELOPMENT_SUMMARY','PARTIAL_INTERMEDIATE_NO_OUTCOME_CONCLUSION'],'Invalid summary')
        require(fr['status']=='PASS_MATCHED_FIGURES_WRITTEN_REQUIRES_VISUAL_REVIEW' and mr['status']=='PASS_STATIC_MAPS','Unverified figures')
        require(receipts['figure_qa']['status']=='PASS_NATIVE_PIXEL_PSNR_AND_BAND_QA' and receipts['map_qa']['status']=='PASS_EXACT_ORIGINAL_DISTANCES_AND_ALL_CELLS','Independent QA required')
        require(sha(roots['figures']/'receipt.json') in hashes(receipts['figure_qa']),'Figure QA binds a different figure packet')
        require(sha(roots['maps']/'receipt.json') in hashes(receipts['map_qa']),'Map QA binds a different map packet')
        # The same evaluation receipt must be shared by summary, figures and maps.
        eval_hashes=[]
        for r in [sr,fr,mr]:
            hs={x['sha256'] for x in r['inputs'] if x['path'].endswith('/receipt.json')}
            eval_hashes.append(hs)
        require(bool(set.intersection(*eval_hashes)),'Analysis bundles do not share an evaluation receipt')
        paired=csv_file(roots['summary'],'paired_summary.csv',sr)
        geometry=csv_file(roots['summary'],'geometry_all_thresholds_raw_post.csv',sr)
        transitions=csv_file(roots['summary'],'paired_all_thresholds_raw_post.csv',sr)
        appearance=csv_file(roots['summary'],'appearance_paired_means.csv',sr)
        for region in bundle['regions']:
            require(region not in regions_seen,'Duplicate region bundle');regions_seen.add(region)
            region_rows=[r for r in paired if r['region']==region and r['mesh_kind']=='raw' and float(r['threshold_m'])==.5]
            require(region_rows,'Empty requested region')
            methods[region]=[r for r in geometry if r['region']==region and r['mesh_kind']=='raw' and float(r['threshold_m'])==.5]
            downloads=[]
            for name in ['paired_summary.csv','geometry_all_thresholds_raw_post.csv','paired_all_thresholds_raw_post.csv','appearance_paired_means.csv','compute.csv']:
                target='downloads/'+region+'_'+name;copy_bound(roots['summary'],name,sr,target);downloads.append(dict(label=name,url=target))
            for row in region_rows:
                condition=row['condition'];key=region+'_'+condition;base=region+'/'+condition
                images={}
                for tab,file in [('roi','matched_camera_roi.png'),('full','matched_camera_full.png'),('section','raw_sections.png')]:
                    images[tab]=copy_bound(roots['figures'],base+'/'+file,fr,'assets/'+key+'_'+file)
                images['map']=copy_bound(roots['maps'],key+'_raw512.png',mr,'assets/'+key+'_map.png')
                case=next(x for x in fr['records'] if x['region']==region and x['condition']==condition)
                rows.append(dict(**row,id=region+'/'+condition,images=images,photograph=case['photograph'],
                    appearance=[x for x in appearance if x['region']==region and x['condition']==condition],
                    geometry=[x for x in geometry if x['region']==region and x['candidate'] in [condition,row['parent_condition']]],
                    transitions=[x for x in transitions if x['region']==region and x['candidate']==condition and x['comparator']==row['parent_condition'] and x['cohort']=='ALL_REFERENCE'],
                    downloads=downloads,source_summary=bundle['summary'],source_figures=bundle['figures'],source_maps=bundle['maps']))
    require(regions_seen=={'P1','P2','P3'} and len({x['id'] for x in rows})==len(rows),'Review must bind all three regions with unique conditions')
    for name in ['index.html','app.js','style.css']:
        bind(a.app/name);shutil.copyfile(a.app/name,out/name)
    rows.sort(key=lambda x:(x['region'],-float(x['lambda_prior']),x['protection']!='native'))
    data=dict(schema='jbgs.local_review_packet.v2',scientific_verdict=None,packet=stamp,
        evaluated_conditions=len(rows),expected_conditions=18,rows=rows,methods=methods,
        positive_f1_conditions=sum(float(x['delta_f1'])>0 for x in rows),negative_f1_conditions=sum(float(x['delta_f1'])<0 for x in rows),
        scope='Same Anchor8k / G versus LC / raw TSDF512 primary / observed UAS support / single development run',
        inputs=list(inputs.values()))
    (out/'data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (out/'sources.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(Path(__file__),out/'build_review_v2.py')
    receipt=dict(status='PASS_REVIEW_PACKET',scientific_verdict=None,evaluated_conditions=len(rows),
                 inputs=list(inputs.values()),outputs=[dict(path=str(x.relative_to(out)),sha256=sha(x)) for x in sorted(out.rglob('*')) if x.is_file()])
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    temporary=a.output/('current_'+stamp+'.tmp');temporary.write_text(json.dumps(dict(packet='packets/'+stamp,receipt_sha256=sha(out/'receipt.json')))+'\n')
    os.replace(temporary,a.output/'current.json')
    print(json.dumps(dict(status=receipt['status'],packet=str(out),evaluated_conditions=len(rows),scientific_verdict=None)))

if __name__=='__main__':main()
