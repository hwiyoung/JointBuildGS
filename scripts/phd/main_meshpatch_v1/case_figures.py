"""Frozen FLOATDIAG cameras/colours applied to before, after and removed crops."""
import ast,struct,gc
import open3d as o3d
from PIL import Image,ImageDraw,ImageFont
from scipy.spatial import cKDTree
from mesh_common import *

def make():
    source=R/'scripts/phd/main_floatdiag_v1/geometry.py'
    cfg=json.loads((R/'configs/phd/main_floatdiag_v1/floatdiag_v1.json').read_text())
    keep=['rgb','glb','reference','gt_grid','grid_values','face_colours','render_context','render']
    nodes=[x for x in ast.parse(source.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in keep]
    ns=dict(np=np,o3d=o3d,json=json,struct=struct,S1=S1,TASK='PHD-MAIN-MESHPATCH-v1',config=lambda:cfg)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),ns)
    font=ImageFont.truetype('/fonts/NotoSansCJK-Regular.ttc',26);small=ImageFont.truetype('/fonts/NotoSansCJK-Regular.ttc',20)
    receipt_path=D/'tables/case_figures.json'
    previous={x['case']:x for x in json.loads(receipt_path.read_text())['cases'] if x['status']=='PASS'} if receipt_path.exists() else {}
    receipts=[]
    for site in ['B0_b10','B173nb_b10','R1rep_b10']:
        cases=json.loads((R/'configs/phd/main_floatdiag_v1'/f'geometry_{site}_ALS.json').read_text())['cases']
        gt,gtpath=ns['reference'](site);e=dict(np.load(LT/'direct_stage1_v2'/f'{site}__ALS/evaluation.npz'))
        origin=np.minimum(gt[:,:2].min(0),e['centre'][:,:2].min(0))-.25;grid=ns['gt_grid'](gt,origin);tree=cKDTree(e['centre'][:,:2]);tau=e['tau']
        for case in cases:
            if case['id'] in previous:
                receipts.append(previous[case['id']]);continue
            needed=[D/'tables/meshes'/f'{site}__ALS__{run}.json' for run in ['nojudge_ALS_s0','lt_dynnow_ALS_s0']]
            if not all(p.exists() and json.loads(p.read_text())['status']=='PASS' for p in needed):
                receipts.append(dict(case=case['id'],status='PENDING',reason='before/after pair not yet complete'));continue
            frames={};stats=[];available=True
            for run in ['nojudge_ALS_s0','lt_dynnow_ALS_s0']:
                receipt=D/'tables/meshes'/f'{site}__ALS__{run}.json'
                if not receipt.exists() or json.loads(receipt.read_text())['status']!='PASS':available=False;continue
                rr=json.loads(receipt.read_text());crops={x['stage']:x for x in rr['case_crops'] if x['case']==case['id']}
                for stage in ['before','after','removed']:
                    crop=crops[stage];p=Path(crop['path'])
                    if crop['empty']:
                        frames[(run,stage)]=[np.full((cam['height'],cam['width'],3),248,np.uint8) for cam in case['cameras']]
                        stats.append(dict(run=run,stage=stage,triangles=0,empty=True));continue
                    mesh=o3d.io.read_triangle_mesh(str(p));colour,info=ns['face_colours'](mesh,grid,origin,tree,tau)
                    context=ns['render_context'](mesh,colour)
                    frames[(run,stage)]=[ns['render'](mesh,colour,cam,context=context) for cam in case['cameras']]
                    del context;gc.collect()
                    web=mesh;voxel=None
                    for val in [.025,.05,.1,.2,.4,.8,1.6,3.2]:
                        if len(web.triangles)<=20000:break
                        web=mesh.simplify_vertex_clustering(val);web.remove_duplicated_vertices();web.remove_degenerate_triangles();web.remove_duplicated_triangles();web.remove_unreferenced_vertices();voxel=val
                    assert len(web.triangles)<=20000
                    col,_=ns['face_colours'](web,grid,origin,tree,tau);dest=D/'figures/web'/f"{case['id']}__{run}__{stage}.glb";dest.parent.mkdir(parents=True,exist_ok=True)
                    ns['glb'](dest,np.asarray(web.vertices)-case['translation'],np.asarray(web.triangles),face_colours=col)
                    stats.append(dict(run=run,stage=stage,source_crop_sha256=sha(p),**info,web_triangles=len(web.triangles),web_voxel=voxel,glb=str(dest)))
                    del mesh,web;gc.collect()
            if not available:
                receipts.append(dict(case=case['id'],status='PENDING',reason='required cleaned mesh receipt absent'));continue
            dest=D/'figures'/case['id'];dest.mkdir(parents=True,exist_ok=True)
            for i,cam in enumerate(case['cameras']):
                W,H=cam['width'],cam['height'];plate=Image.new('RGB',(W*3,H*2+160),'white');draw=ImageDraw.Draw(plate)
                draw.text((20,8),f"{case['id']} · 시점 {i+1} · 정리 전 / 정리 후 / 지운 면",font=font,fill='#222222')
                for j,run in enumerate(['nojudge_ALS_s0','lt_dynnow_ALS_s0']):
                    for k,stage in enumerate(['before','after','removed']):plate.paste(Image.fromarray(frames[(run,stage)][i]),(W*k,70+j*(H+30)))
                    draw.text((20,46+j*(H+30)),['판정 끔','판 4'][j],font=small,fill='#222222')
                draw.text((20,H*2+110),'빨강: 참값보다 τ 위 · 회색: τ 안 · 파랑: 그 밖 · 연회색: 참값 확인 불가',font=small,fill='#222222')
                plate.save(dest/f'view_{i+1}.png',optimize=True)
            receipts.append(dict(case=case['id'],status='PASS',views=len(case['cameras']),cameras=case['cameras'],translation=case['translation'],rows=stats,
                note='Colours reproduce the original FLOATDIAG display rule, which differs from the quantitative five-category first-hit rule. Removed faces are displayed separately, with the same colours.'))
    dump(D/'tables/case_figures.json',dict(cases=receipts,source_sha256=sha(source),scientific_verdict=None,provenance='[이 발주에서 냄]'))

if __name__=='__main__':make()
