"""Additive display-only export of verified, already evaluated LC surfaces."""
import argparse,copy,hashlib,json,os,platform,shutil,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'geogs_p1p2p3_v1/evaluation'))
from display_export import export_clipped_mesh,binary_array
from geometry import voxel_reference

def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as s:
        for b in iter(lambda:s.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def require(ok,why):
    if not ok:raise ValueError(why)
def write(p,v):
    with Path(p).open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def safe(root,name):
    p=(root/name).resolve();require(p.is_relative_to(root.resolve()),'Path escaped source');return p

def main():
    ap=argparse.ArgumentParser()
    for k in ['task','parent-evaluation','app','output']:ap.add_argument('--'+k,type=Path,required=True)
    a=ap.parse_args();require(Path('/.dockerenv').is_file(),'Docker required');start=time.time();inputs={}
    def bind(p,expected=None):
        h=sha(p);require(expected is None or expected==h,'Input digest differs: '+str(p))
        inputs[str(p)]=dict(path=str(p),sha256=h,bytes=p.stat().st_size);return h
    current=read(a.task/'review_site/current.json');static=safe(a.task/'review_site',current['packet'])
    bind(static/'receipt.json',current['receipt_sha256']);sr=read(static/'receipt.json')
    require(sr['status']=='PASS_REVIEW_PACKET' and sr['scientific_verdict'] is None,'Verified review packet required')
    for n in ['data.json','sources.json']:
        rec=next(x for x in sr['outputs'] if x['path']==n);bind(static/n,rec['sha256'])
    data=read(static/'data.json');sources=read(static/'sources.json')
    oldpath=a.parent_evaluation/'viewer/manifest_v2.json';bind(oldpath);old=read(oldpath)
    require(old['scientific_verdict'] is None,'Parent technical review only')
    packet='packet_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out=a.output/'packets'/packet;out.mkdir(parents=True,exist_ok=False)
    cache=a.output/'cache';cache.mkdir(exist_ok=True)
    evaluations={};eval_index={sha(p):p.parent for p in (a.task/'evaluation').glob('*/receipt.json')}
    for b in sources['bundles']:
        summary=safe(a.task,b['summary'])/'receipt.json';bind(summary);receipt=read(summary)
        ehash=next(x['sha256'] for x in receipt['inputs'] if x['path']=='/evaluation/receipt.json')
        require(ehash in eval_index,'Evaluation hash not found');e=eval_index[ehash];bind(e/'receipt.json',ehash)
        for region in b['regions']:evaluations[region]=(e,read(e/'receipt.json'))
    created=0;reused=0;records=[];regions=[]
    def parent_candidate(c):
        c=copy.deepcopy(c);c['downloads']=[]
        d=c.get('data')
        if d:
            p=safe(a.parent_evaluation/'viewer',d['url']);bind(p,d.get('sha256'));d['url']='/parent/viewer/'+str(p.relative_to(a.parent_evaluation/'viewer'))
        md=c.get('mesh_data')
        if md:
            p=safe(a.parent_evaluation/'viewer',md['url']);bind(p,md.get('sha256'));m=read(p)
            for k in ['vertices_f64','triangles_u32']:
                z=safe(a.parent_evaluation/'viewer',m[k]['url']);bind(z,m[k]['sha256']);m[k]['url']='/parent/viewer/'+str(z.relative_to(a.parent_evaluation/'viewer'))
            rel='parent_'+c['id']+'.mesh.json';dest=out/current_region/rel;dest.parent.mkdir(exist_ok=True)
            write(dest,m);c['mesh_data']=dict(format='json',url=current_region+'/'+rel,sha256=sha(dest),bytes=dest.stat().st_size)
        return c
    for spec in old['regions']:
        current_region=spec['id'];rows=[r for r in data['rows'] if r['region']==current_region];require(rows,'Region has no evaluated conditions')
        e,er=evaluations[current_region];output_index={r['path']:r for r in er['outputs']}
        desired={'prior_mesh','als_points','mvs_points','reference'}|{'D005_Pnative.anchor_512.'+k for k in ['raw','post']}
        desired|={r['parent_condition']+'.mesh_512.'+k for r in rows for k in ['raw','post']}
        candidates=[parent_candidate(c) for c in spec['candidates'] if c['id'] in desired]
        require({c['id'] for c in candidates}==desired,'Parent candidate missing')
        conditions=[];sections=[];renders=[]
        for row in rows:
            cid=row['condition'];parent=row['parent_condition']
            conditions.append(dict(id=cid,label=f"{cid} · prior {row['lambda_prior']} · {row['protection']}",candidate_id=cid+'.mesh_512.raw',parent_candidate_id=parent+'.mesh_512.raw',scientific_verdict=None))
            for kind in ['raw','post']:
                prefix=current_region+'/'+cid+'/'+kind;npz=e/(prefix+'_distances.npz');mp=e/(prefix+'_metrics.json')
                nh=bind(npz,output_index[prefix+'_distances.npz']['sha256']);mh=bind(mp,output_index[prefix+'_metrics.json']['sha256']);metric=read(mp)
                require(metric['scientific_verdict'] is None and metric['mesh_res']==512,'Exact evaluated TSDF512 required')
                key=hashlib.sha256((nh+mh+'lc3d_v2_fixedcolor_voxel01_cap200k').encode()).hexdigest();dest=cache/key
                if (dest/'receipt.json').is_file():
                    cr=read(dest/'receipt.json');require(cr['npz_sha256']==nh and cr['metric_sha256']==mh,'Cache lineage differs')
                    for rec in cr['outputs']:require(sha(dest/rec['path'])==rec['sha256'],'Cache altered')
                    reused+=1
                else:
                    require(not dest.exists(),'Incomplete export cache preserved');dest.mkdir()
                    with np.load(npz,allow_pickle=False) as z:arrays={k:z[k] for k in z.files}
                    pts=arrays['prediction_surface_samples'];_,picked=voxel_reference(pts,.1);nvoxel=len(picked)
                    if len(picked)>200000:picked=picked[np.linspace(0,len(picked)-1,200000,dtype=np.int64)]
                    recxyz=binary_array(dest/'points.xyz.f32',pts[picked],'<f4');recd=binary_array(dest/'points.distance.f32',arrays['prediction_to_reference_distance'][picked],'<f4')
                    recxyz['url']='/cache/'+key+'/points.xyz.f32';recd['url']='/cache/'+key+'/points.distance.f32'
                    points=dict(display_only=True,scientific_verdict=None,surface_kind='triangle_surface',xyz_f32=recxyz,distance_f32=recd,
                        display_sample_count=len(picked),full_evaluation_sample_count=len(pts),original_points_in_roi=None,
                        source_path=str(npz),sampling_metadata=dict(evaluation_kind='AREA_UNIFORM_TRIANGLE_SURFACE_SAMPLES',display_voxel_m=.1,display_voxel_selected_count=nvoxel,display_cap=200000,display_cap_applied=nvoxel>200000,never_used_in_scoring=True),
                        color_provenance=dict(kind='FIXED_SOURCE_COLOR',description='LC source color only; height mode shows geometry. RGB assessment uses saved photo comparisons.'),color=[66,127,183])
                    write(dest/'points.json',points)
                    original=next(x for x in er['inputs'] if x.get('sha256')==metric['source_sha256'])
                    source=dict(path=original['path'],sha256=original['sha256'],bytes=original.get('bytes'),scope='FULL_CAMERA_BOUNDED_TSDF_EXTRACTION',source_kind='OFFICIAL_GEOGS_TSDF_MESH',evaluation_crop_separate=True)
                    mesh=export_clipped_mesh(dest/'mesh.json',arrays,metric['bounds_half_open'],source,[66,127,183],a.output,metric)
                    mm=read(dest/'mesh.json')
                    for field in ['vertices_f64','triangles_u32']:mm[field]['url']='/'+mm[field]['url']
                    # Metadata URL qualification only, before this new cache is sealed.
                    (dest/'mesh.json').write_text(json.dumps(mm,indent=2,allow_nan=False)+'\n')
                    cr=dict(status='PASS_EXACT_EVALUATED_DISPLAY_EXPORT',scientific_verdict=None,npz_sha256=nh,metric_sha256=mh,
                        topology_exact=True,source_npz=str(npz),source_metric=str(mp),new_geometry_extraction=False,new_scoring=False,
                        outputs=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in sorted(dest.iterdir()) if p.is_file()])
                    write(dest/'receipt.json',cr);created+=1;del arrays
                with np.load(npz,allow_pickle=False) as z:
                    vertices=z['clipped_vertices'];triangles=z['clipped_triangles']
                    require(np.array_equal(np.fromfile(dest/'mesh.vertices.f64',dtype='<f8').reshape(-1,3),vertices),'Exported vertices differ from evaluated NPZ')
                    require(np.array_equal(np.fromfile(dest/'mesh.triangles.u32',dtype='<u4').reshape(-1,3),triangles),'Exported triangles differ from evaluated NPZ')
                identifier=cid+'.mesh_512.'+kind
                display_status='reconstruction_failure' if metric['status']=='RECONSTRUCTION_FAILURE' else 'available'
                candidates.append(dict(id=identifier,label=cid+' · '+kind,status=display_status,role='changed',surface_kind='triangle_surface',
                    data=dict(format='json',url='/cache/'+key+'/points.json'),mesh_data=dict(format='json',url='/cache/'+key+'/mesh.json'),
                    provenance=dict(evaluation_receipt_sha256=sha(e/'receipt.json'),evaluated_npz_sha256=nh,metric_sha256=mh),
                    downloads=[dict(label='평가 원 수치',url='/task/'+str(mp.relative_to(a.task))),dict(label='표시 계보',url='/cache/'+key+'/receipt.json')]))
                records.append(dict(region=current_region,condition=cid,kind=kind,candidate_id=identifier,parent_candidate_id=parent+'.mesh_512.'+kind,cache_key=key,npz_sha256=nh,
                    display_status=display_status,all_exported_vertices_and_triangles_equal_evaluated_npz=True,vertices=len(vertices),triangles=len(triangles)))
            images=row['images'];base='/task/review_site/'+current['packet']+'/'
            sections.append(dict(id=cid+'.raw',condition_id=cid,label=cid+' · 고정 단면 raw512',url=base+images['section'],caption='Anchor / 동일 G / LC / UAS · 기존 평가의 동일 위치와 폭 표본 띠. 실제 교선이 아닙니다.'))
            for kind,label in [('roi','동일 사진 ROI'),('full','동일 사진 전체')]:renders.append(dict(id=cid+'.'+kind,condition_id=cid,label=label,url=base+images[kind],domain=kind,image_name=row['photograph'],caption='원 사진과 기존 G 및 LC의 같은 카메라 렌더 비교.'))
        regions.append(dict(id=current_region,label=current_region,bounds=spec['bounds'],frame=spec['frame'],notes=['기존 평가의 동일 XYZ 범위. GT는 평가 전용. 단일 실행의 개발 비교입니다.'],
            candidates=candidates,conditions=conditions,default_condition=conditions[0]['id'],panel_candidates=dict(prior='prior_mesh',mvs='mvs_points',anchor='D005_Pnative.anchor_512.raw',vanilla=rows[0]['parent_condition']+'.mesh_512.raw',reference='reference'),
            sections=sections,renders=renders,cases=[],downloads=[]))
    manifest=dict(schema='geogs_p1p2p3_viewer_v1',scientific_verdict=None,title='국소 상보 LC · 동일 G 3D 비교',default_region='P1',default_resolution='512',
        resolution_modes=[dict(id='512',mesh_res=512,anchor_variant='anchor_512',final_variant='mesh_512',label='동일 TSDF512')],regions=regions,
        notes=['화면용 점/메시를 평가에 재입력하지 않습니다. 소스별 고정색과 높이색은 관측 RGB가 아닙니다. 평균 배율 전역 대조·controller replay·반복은 없습니다.'],
        downloads=[dict(label='정성·정량 결과 화면',url='http://localhost:8905'),dict(label='이번 3D 표시 계보',url='receipt.json')],
        evaluated_conditions=len(data['rows']),source_review_packet=current['packet'],source_review_receipt_sha256=current['receipt_sha256'])
    write(out/'manifest.json',manifest)
    for p in a.app.iterdir():
        if p.is_file():bind(p);shutil.copyfile(p,out/p.name)
    bind(Path(__file__));shutil.copyfile(Path(__file__),out/'build_review_3d_v2.py')
    for helper in ['display_export.py','geometry.py']:
        source=Path(__file__).resolve().parents[1]/'geogs_p1p2p3_v1/evaluation'/helper
        bind(source);shutil.copyfile(source,out/helper)
    bind(Path(__file__).with_suffix('.sh'));shutil.copyfile(Path(__file__).with_suffix('.sh'),out/'build_review_3d_v2.sh')
    receipt=dict(status='PASS_3D_EXPORT_BROWSER_REVIEW_REQUIRED',scientific_verdict=None,evaluated_conditions=len(data['rows']),created_exports=created,reused_exports=reused,records=records,
        source_review_packet=current['packet'],source_review_receipt_sha256=current['receipt_sha256'],inputs=list(inputs.values()),wall_seconds=time.time()-start,python=platform.python_version(),numpy=np.__version__,new_training=False,new_geometry_extraction=False,new_scoring=False,
        outputs=[dict(path=str(p.relative_to(out)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.rglob('*')) if p.is_file()])
    write(out/'receipt.json',receipt);tmp=a.output/(packet+'.tmp');write(tmp,dict(packet='packets/'+packet,receipt_sha256=sha(out/'receipt.json')));os.replace(tmp,a.output/'current.json')
    print(json.dumps(dict(status=receipt['status'],packet=str(out),evaluated_conditions=len(data['rows']),created_exports=created,reused_exports=reused,scientific_verdict=None)))

if __name__=='__main__':main()
