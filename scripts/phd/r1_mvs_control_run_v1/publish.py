"""Publish only validated R1 artifacts; watch immutable stage receipts."""
import copy,hashlib,json,shutil,time,traceback
from pathlib import Path
import numpy as np
from plyfile import PlyData
from export_geometry import export_points,_clip_mesh,_sample_mesh,_binary,_point_buffers

root=Path('/out');run=Path('/run');review=Path('/review');root.mkdir(exist_ok=True)
u=np.array([np.cos(np.deg2rad(70)),np.sin(np.deg2rad(70))]);v=np.array([u[1],-u[0]])
box=np.array([[-135,-35,-90],[70,65,80]],float)
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def atomic(p,value):
    p=Path(p);temp=p.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False));temp.replace(p)
def transform(xyz):return np.column_stack((xyz[:,:2]@u,-xyz[:,:2]@v,xyz[:,2]))
def qualify(value,prefix):
    if isinstance(value,dict):return {k:prefix+v if k=='url' and isinstance(v,str) else qualify(v,prefix) for k,v in value.items()}
    if isinstance(value,list):return [qualify(v,prefix) for v in value]
    return value
def cache(key,factory):
    dest=root/'cache'/key;receipt=dest/'export.json'
    if not receipt.exists():
        data=factory(dest);data.update(coordinate_frame='DISPLAY_OBJECT_FRAME: x=u, y=-v, z=source local z; u=70deg; raw inputs unchanged',scientific_verdict=None)
        atomic(receipt,data)
    return qualify(read(receipt),f'/data/cache/{key}/')
def points(xyz,rgb,dest,kind,color):
    return export_points(transform(xyz),rgb,dest,bounds={'min':box[0].tolist(),'max':box[1].tolist()},point_cap=250000,geometry_kind=kind,color=color)
def candidate(id,label,group,data=None,**kw):return dict(id=id,label=label,group=group,status=kw.pop('status','available' if data else 'pending'),**(data or {}),**kw)
def geometry(path,dest,mesh=False):
    ply=PlyData.read(path,mmap='r');verts=ply['vertex'];xyz=np.column_stack([verts[k] for k in 'xyz'])
    if not mesh:
        dc=np.column_stack([verts['f_dc_'+str(i)] for i in range(3)]);rgb=np.clip(.5+.28209479177387814*dc,0,1)*255
        return points(xyz,rgb,dest,'GAUSSIAN_CENTERS',{'kind':'SH_DC_COLOR','label':'Gaussian 중심 · SH 기본색'})
    rgb=np.column_stack([verts[k] for k in ('red','green','blue')]);faces=np.array(list(ply['face']['vertex_indices']),dtype=np.int64)
    xyz,rgb,faces,n=_clip_mesh(transform(xyz),rgb,faces,box)
    assert len(faces)>0 and np.isfinite(xyz).all()
    px,prgb,area=_sample_mesh(xyz,rgb,faces,200000);dest.mkdir(parents=True)
    return dict(points=_point_buffers(dest,px,prgb),mesh=dict(xyz=_binary(dest,'mesh.xyz',xyz,'<f4'),rgb=_binary(dest,'mesh.rgb',np.rint(rgb),'u1'),indices=_binary(dest,'mesh.indices',faces,'<u4'),vertex_count=len(xyz),triangle_count=len(faces)),geometry_kind='NATIVE_RGB_TRIANGLE_MESH',color={'kind':'NATIVE_VERTEX_RGB','label':'추출 표면 정점 RGB'},sampling={'cropped_surface_area_m2':area,'displayed_count':len(px),'point_cap':200000},evaluation_reinput=False)
def main():
    expected='eadce291ee2d580ab62595758433039c45a3572494131ac2a15cdafb03946d78';assert sha(review/'receipt.json')==expected
    rr=read(review/'receipt.json')
    for name,digest in rr['files'].items():assert sha(review/name)==digest,name
    j=np.load(review/'surface_judgments.npz');ev=np.load('/evidence/surface_evidence.npz');cfg=read(review/'config.json')
    (root/'cache').mkdir(exist_ok=True)
    if not (root/'judgment').exists():
        (root/'judgment').mkdir()
        for name in ('R1_whole_area_judgment.png','zone_judgments.csv','zone_review_1.png','zone_review_2.png','zone_review_3.png','zone_review_4.png'):shutil.copy2(review/name,root/'judgment'/name)
    base=[candidate('prior','ALS prior 표본 · 회색','prior',cache('prior',lambda d:points(ev['prior_xyz'],np.tile([180,190,198],(len(ev['prior_xyz']),1)),d,'ALS_PRIOR_POINTS',{'kind':'CONSTANT_NEUTRAL','label':'회색 · 기하 확인용'}))),candidate('mvs','융합 MVS · 원본 RGB','mvs',cache('mvs',lambda d:points(ev['mvs_xyz'],ev['mvs_rgb'],d,'FUSED_MVS_POINTS',{'kind':'NATIVE_MVS_RGB','label':'MVS 원본 RGB'})))]
    palette=np.array([[154,157,163],[39,135,186],[230,160,26],[154,89,181],[71,123,85]])
    base.append(candidate('judgment','현재 표면 · 판단 초안','mvs',cache('judgment',lambda d:points(ev['mvs_xyz'],palette[j['judgment'][:len(ev['mvs_xyz'])]],d,'INPUT_JUDGMENT_POINTS',{'kind':'JUDGMENT_CATEGORIES','label':'보존·보정·보완·비대상 후보·유보'}))))
    while True:
        try:
            items=copy.deepcopy(base);mesh_run=run
            if (run/'mesh_recovery.json').exists():
                binding=read(run/'mesh_recovery.json');mesh_run=(run/binding['relative']).resolve()
                assert mesh_run.is_relative_to(run.resolve()) and mesh_run!=run.resolve()
            state=(mesh_run/'status.txt').read_text().strip() if (mesh_run/'status.txt').exists() else '대기'
            progress={};records={}
            for stage,iteration,role,label,ext in [('anchor',8000,'anchor','Anchor · 8,000회','extract_anchor'),('refinement',30000,'mvs_geogs','MVS–GeoGS · 30,000회','extract_final')]:
                receipt=run/stage/'receipt.json';r=read(receipt) if receipt.exists() else None
                if (run/stage/'progress.json').exists():progress=read(run/stage/'progress.json')
                if r and r['status']=='PASS':
                    records[stage]=r;path=run/stage/'model/jbgs_complete'/f'iteration_{iteration}'/'point_cloud.ply';digest=r['checkpoint']['ply_sha256']
                    assert sha(path)==digest
                    data=cache(stage+'_'+digest[:16],lambda d:geometry(path,d))
                    items.append(candidate(stage+'_centers',label+' · Gaussian 중심',role,data))
                    er=mesh_run/ext/'receipt.json'
                    if er.exists() and read(er)['status']=='PASS':
                        rec=read(er)['surfaces']['fuse.ply'];p=mesh_run/ext/rec['path'];assert sha(p)==rec['sha256']
                        data=cache(ext+'_'+rec['sha256'][:16],lambda d:geometry(p,d,True))
                        items.append(candidate(stage+'_mesh',label+' · RGB 표면',role,data))
                else:items.append(candidate(stage+'_pending',label,role,reason='학습·검증 대기' if not r else r.get('error','단계 실패'),status='failed' if r else 'pending'))
            defaults={role:next((c['id'] for c in reversed(items) if c['group']==role and c['status']=='available'),next(c['id'] for c in items if c['group']==role)) for role in ('prior','mvs','anchor','mvs_geogs')};defaults['mvs']='mvs'
            xyz=transform(ev['mvs_xyz']);bounds={'min':[-135,-35,float(xyz[:,2].min())],'max':[70,65,float(xyz[:,2].max())]}
            regions=[dict(id='R1',bounds=bounds,frame='객체축 u / -v / local z · m',candidates=items,default_candidates=defaults)]
            for z in sorted(cfg['zones'],key=lambda z:z['id']):
                if z['id']=='Z00':continue
                p=np.array(z['polygon']);mn=p.min(0);mx=p.max(0);inside=(xyz[:,0]>=mn[0])&(xyz[:,0]<=mx[0])&(-xyz[:,1]>=mn[1])&(-xyz[:,1]<=mx[1]);zz=xyz[inside,2]
                zb={'min':[float(mn[0]),float(-mx[1]),float(np.min(zz)) if len(zz) else bounds['min'][2]],'max':[float(mx[0]),float(-mn[1]),float(np.max(zz)) if len(zz) else bounds['max'][2]]}
                regions.append(dict(id=z['id'],bounds=zb,frame=z['name']+' · 주변 표면 함께 표시',candidates=items,default_candidates=defaults))
            labels={'verify':'봉인 입력 검증 중','anchor':'초기 상태 학습 중','preflight':'MVS 재개 점검 중','refinement':'MVS 대조군 학습 중','extract_final':'최종 표면 추출 중','extract_anchor':'초기 상태 표면 추출 중','COMPLETE':'학습·표면 추출 완료'}
            status=dict(stage=state,progress=progress,receipts=list(records),scientific_verdict=None,training_condition='MVS / prior .005 / native protection / no manual weights',updated_unix=time.time())
            atomic(root/'status.json',status)
            atomic(root/'manifest.json',dict(schema='geogs_rgb_comparison_v1',scientific_verdict=None,built_at=time.time(),regions=regions,run_status={'queue_status':labels.get(state,state),'completed':progress.get('iteration',0),'total':30000},report='/data/status.json'))
        except Exception:
            with (root/'publication_errors.log').open('a') as f:f.write(traceback.format_exc()+'\n')
            atomic(root/'publication_failure.json',dict(status='FAIL',error=traceback.format_exc(),scientific_verdict=None))
            if (root/'manifest.json').exists():
                failed=read(root/'manifest.json');failed['run_status']['queue_status']='뷰어 결과 갱신 실패 · 실행 기록 확인';atomic(root/'manifest.json',failed)
        time.sleep(30)

if __name__=='__main__':main()
