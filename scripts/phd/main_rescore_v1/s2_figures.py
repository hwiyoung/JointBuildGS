"""Regional chapter-7 figures at inherited section positions and fixed camera angles.
Only display caches are new; no virtual camera is passed to mesh reconstruction.
"""
from common import *
import types, sys, gc
from geometry import context, MeshScene
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'

def bind(site):
    cfg(); dest=C/f'addendum3_stage2_{site}_figures.json'
    if dest.exists(): return
    old=C/'input_sections_v1.json'
    first=next(r.copy() for r in json.loads(old.read_text())['rows'] if r['site']==site)
    first.update(id='A',name='모임지붕 끝' if site=='B0_b10' else '지붕',roi_half_width=3.)
    source=R/'configs/phd/main_stage1_v1/sections_v1.json'
    section_id='B0_wall_eaves' if site=='B0_b10' else 'R1_translucent'
    s=json.loads(source.read_text())['sections'][section_id];c=np.array(s['centre']);t=np.array(s['t'])
    second=dict(id='B',name='정면과 처마' if site=='B0_b10' else '채광 지붕',start=(c[:2]-t*s['L']/2).tolist(),end=(c[:2]+t*s['L']/2).tolist(),half_width=s['half_width_m'],roi_half_width=3.,anchor_xyz=c.tolist(),source=str(source),source_sha256=sha(source),section_id=section_id)
    places=[first,second]
    for row in places:
        row['labels_by_prior']={}
        for prior in ['ALS','LoD2']:
            z=loadz(JA/'core_points'/f'{site}__{prior}.npz',['centre','area','kind'])
            codes=loadz(CELLS/f'{site}__{prior}.npz',['cell_v2'])['cell_v2']
            a,b=np.array(row['start']),np.array(row['end']);d=(b-a)/np.linalg.norm(b-a);delta=z['centre'][:,:2]-a
            length=delta@d;off=np.abs(delta[:,0]*d[1]-delta[:,1]*d[0]);take=(length>=0)&(length<=np.linalg.norm(b-a))&(off<=row['half_width'])
            if row['id']=='A' or site=='R1rep_b10':take&=z['kind']==1
            areas={str(k):float(z['area'][take&(codes==k)].sum()) for k in np.unique(codes)}
            eligible={k:v for k,v in areas.items() if int(k) in range(5)}
            chosen=int(max(eligible,key=eligible.get)) if eligible and max(eligible.values())>0 else None
            row['labels_by_prior'][prior]=dict(cell=chosen,cell_area_m2=areas,label_rule='dominant evaluable correct cell by area in the inherited section band; roof only except B0 facade/eaves; values use that cell over the whole region')
    record=dict(site=site,rows=places,source_sections=[dict(path=str(p),sha256=sha(p)) for p in [old,source]],shared_across_priors=True,camera=dict(azimuth_deg=-60,elevation_deg=35,projection='orthographic',source='/repo/scripts/phd/main_rescore_v1/figures.py:frame',purpose='display only; no TSDF integration'),scientific_verdict=None)
    dump(dest,record);print('FIGURE_POSITIONS',site,[r['labels_by_prior'] for r in places],flush=True)

def module(site, only73=False):
    source=Path(__file__).with_name('figures.py');text=source.read_text()
    text=text.replace("C/'representatives_v1.json'", "C/"+repr(f'addendum3_stage2_{site}_figures.json'))
    text=text.replace("TG/'r8/targets'/f'{SITE}_{prior}.npz'", "FT/'targets'/f'{SITE}__{prior}.npz'")
    text=text.replace("'본 방법 · '+method", "'본 방법 · FINALTRAIN 30,000회'")
    text=text.replace('r8 임시','FINALTRAIN 30,000회').replace('provisional=True','provisional=False')
    text=text.replace("plt.subplots(3,5,figsize=(21,12)","plt.subplots(len(places),5,figsize=(21,4*len(places))")
    text=text.replace("x['cell']==2);ax.set_title(f\"보존이 맞는 영역 전체 완전성", "x['cell']==row['labels_by_prior'][prior]['cell']);ax.set_title(f\"{CELL[row['labels_by_prior'][prior]['cell']]} 영역 전체 완전성")
    text=text.replace('dict(family=family,cell2=m)','dict(family=family,cell=m)')
    text=text.replace('xlim=(0,10)','xlim=(0,np.linalg.norm(np.array(row["end"])-row["start"]))')
    text=text.replace("b173_table", site+'_table')
    if only73:
        marker="\n fig,axes=plt.subplots(len(places),5,figsize=(21,4*len(places))"
        assert marker in text
        text=text.replace(marker,"\n return"+marker,1)
    m=types.ModuleType('stage2_figures');m.__file__=str(source);m.FT=FT
    exec(compile(text,str(source),'exec'),m.__dict__);m.SITE=site
    old=m.artifact
    def artifact(fig,name,meta):
        if site=='R1rep_b10' and name.startswith('그림7_3_'):
            # axis('off') captions were omitted by constrained-layout. Reserve
            # explicit figure rows for titles and numbers without changing views.
            fig.set_layout_engine(None);fig.set_size_inches(17,8.5)
            labels=[]
            for i,ax in enumerate(fig.axes):
                row,col=divmod(i,4);x=.018+col*.245;center=x+.115
                title=ax.get_title();ax.set_title('')
                labels.append(fig.text(center,.875 if row==0 else .425,title,ha='center',va='bottom',fontsize=10))
                ax.set_position([x,.54 if row==0 else .10,.23,.30])
                caption=next(t for t in ax.texts if t.get_text().startswith(('완전성 ','정확성 ')))
                caption.set_transform(fig.transFigure);caption.set_position((center,.515 if row==0 else .075));caption.set_clip_on(False);labels.append(caption)
            fig._suptitle.set_y(.985);labels.append(fig._suptitle)
            fig.set_dpi(300);fig.canvas.draw();renderer=fig.canvas.get_renderer()
            boxes=[t.get_window_extent(renderer) for t in labels]
            assert all(b.x0>=0 and b.y0>=0 and b.x1<=fig.bbox.width and b.y1<=fig.bbox.height for b in boxes)
            assert all(not a.overlaps(b) for i,a in enumerate(boxes) for b in boxes[i+1:])
            meta['layout_check']=dict(status='PASS',rule='all 17 title/caption bounding boxes inside canvas and pairwise disjoint at 300 dpi',boxes_px=[b.extents.tolist() for b in boxes],repair='explicit display rows; cached surfaces, scores, camera and colors unchanged')
        n=len(json.loads((O/'views'/f'{site}.json').read_text())['views'])
        meta.update(site=site,mesh_rule=f'{n} training views, TSDF .05/.25 m, top50 and evaluation crop',provisional=False,adapter_sha256=sha(__file__),source_sha256=sha(source),places_config_sha256=sha(C/f'addendum3_stage2_{site}_figures.json'))
        old(fig,site+'__'+name,meta)
    m.artifact=artifact;return m

def prepare(site,prior):
    cfg();m=module(site);method=f'{site}__{prior}__FINALTRAIN_30000'
    places=json.loads((C/f'addendum3_stage2_{site}_figures.json').read_text())['rows']
    assert all(r['labels_by_prior'][prior]['cell'] is not None for r in places)
    cache=O/'figure_cache'/prior/method;cache.mkdir(parents=True,exist_ok=True)
    ctx=context(site,prior);gt=ctx['gt'].Gb;box=np.array(json.loads((O/'views'/f'{site}.json').read_text())['box'])
    frames={'all':m.frame(box)};frames.update({r['id']:m.frame(m.roi_box(r,gt),650,500) for r in places})
    dump(cache/'frames.json',{k:m.serial_frame(v) for k,v in frames.items()})
    for family in ['prior','mvs','fusion','baseline_30000','method']:
        if (cache/(family+'.npz')).exists():continue
        if not (O/'scores'/m.key(prior,family,method)/'values.json').exists():continue
        v=m.value(prior,family,method);points=loadz(O/'scores'/v['key']/'points.npz',['scene_distance_m','scene_tau_m'])
        V,F=m.read_surface(v['mesh']);scene=MeshScene(V,F)
        data=dict(all_gt=m.gt_image(gt,points['scene_distance_m'],points['scene_tau_m'],frames['all']),all_result=m.render_mesh(scene,ctx,frames['all'],cache/(family+'_all_columns')))
        for row in places:
            im=m.render_mesh(scene,ctx,frames[row['id']],cache/(family+'_'+row['id']+'_columns'))
            data[row['id']+'_image']=m.gt_image(gt,points['scene_distance_m'],points['scene_tau_m'],frames[row['id']],im,True)
            data[row['id']+'_section']=m.section_segments(V,F,row)
        savez(cache/(family+'.npz'),**data);del V,F,scene;gc.collect();print('FIGURE_CACHE',site,prior,family,flush=True)
    savez(cache/'reference.npz',**{r['id']+'_gt':m.section_points(gt,r) for r in places})
    pending=[f for f in ['prior','mvs','fusion','baseline_30000','method'] if not (cache/(f+'.npz')).exists()]
    dump(cache/'receipt.json',dict(status='PENDING_SCORES' if pending else 'PASS',pending=pending,site=site,prior=prior,method=method,source_sha256=sha(__file__),places_sha256=sha(C/f'addendum3_stage2_{site}_figures.json'),scientific_verdict=None))

if __name__=='__main__':
    mode,site=sys.argv[1:3]
    if mode=='bind':bind(site)
    elif mode=='prepare':prepare(site,sys.argv[3])
    elif mode=='draw':
        prior=sys.argv[3];m=module(site);method=f'{site}__{prior}__FINALTRAIN_30000';m.draw_early(prior,method);m.draw_remaining(prior,method)
    elif mode=='draw73':
        prior=sys.argv[3];m=module(site,only73=True);m.draw_early(prior,f'{site}__{prior}__FINALTRAIN_30000')
    else:raise ValueError(mode)
