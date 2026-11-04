"""Reuse RESCORE figure calculations and layouts with FINALTRAIN data bindings.

Only source/output bindings, method labels and absent-comparison placeholders
are adapted. The original figure source is never written.
"""
import ast,copy,gc,sys,time,types
from common import *
RS=PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'

def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,float) and not np.isfinite(value):return None
    return value

def representatives(site,root):
    source=R/'configs/phd/main_rescore_v1/representatives_v1.json'
    if site=='B173nb_b10':value=json.loads(source.read_text())
    else:
        old=R/'configs/phd/main_target_v1/representatives_v1.json';rows=[]
        for oldrow in json.loads(old.read_text())['rows']:
            if oldrow['site']!=site:continue
            row={k:oldrow[k] for k in ['name','start','end','half_width']}
            row.update(id=chr(65+len(rows)),roi_half_width=3.,source=str(old),source_sha256=sha(old),original_id=oldrow['id'],labels_by_prior={})
            a,b=np.asarray(row['start']),np.asarray(row['end']);direction=(b-a)/np.linalg.norm(b-a)
            for prior in ['ALS','LoD2']:
                core=loadz(JA/'core_points'/f'{site}__{prior}.npz',['centre','kind','area']);cell=loadz(RS/'cells_v2'/f'{site}__{prior}.npz',['cell_v2'])['cell_v2']
                delta=core['centre'][:,:2]-a;s=delta@direction;off=abs(delta[:,0]*direction[1]-delta[:,1]*direction[0]);mask=(core['kind']==1)&(s>=0)&(s<=np.linalg.norm(b-a))&(off<=row['half_width'])
                areas={int(k):float(core['area'][mask&(cell==k)].sum()) for k in np.unique(cell[mask])};valid={k:v for k,v in areas.items() if k in [0,1,2,3,4]}
                assert valid,'No defined reference cell in inherited representative section'
                row['labels_by_prior'][prior]=dict(cell=max(valid,key=valid.get),cell_area_m2=areas,label_rule='dominant defined roof cell in inherited fixed section; whole evaluation-cell metric')
            rows.append(row)
        assert rows;value=dict(site=site,shared_across_priors=True,rows=rows,note='B173 A/B/C are outside this site; use existing r8 fixed sections, without choosing from the new result.',scientific_verdict=None)
    dump(root/'representatives_v1.json',value);return value

def main(site,prior,mode='early'):
    cfg();stem=f'{site}__{prior}';method='ft_'+stem;root=O/'figure_jobs'/stem;root.mkdir(parents=True,exist_ok=True)
    from rescore_bridge import bind
    mod,source=bind();mod.O=root;mod.C=root/'config';mod.C.mkdir(exist_ok=True);mod.D=D
    for name in ['rescore_v1.json','rescore_v1.initial.lock.json']:
        dest=mod.C/name;original=R/'configs/phd/main_rescore_v1'/name
        if not dest.exists():dest.symlink_to(original)
    places=representatives(site,mod.C)
    scores=root/'scores';scores.mkdir(exist_ok=True)
    for p in (RS/'scores').glob(site+'__'+prior+'__*/values.json'):
        dest=scores/p.parent.name
        if not dest.exists():dest.symlink_to(p.parent,target_is_directory=True)
    dest=scores/method
    if not dest.exists():dest.symlink_to(O/'rescore/scores'/method,target_is_directory=True)
    path=source/'figures.py';text=path.read_text()
    old="TG/'r8/targets'/f'{SITE}_{prior}.npz'"
    assert old in text,'RESCORE target source interface changed'
    text=text.replace(old,'FINAL_TARGET')
    text=text.replace('r8 임시','FINALTRAIN')
    text=text.replace('plt.subplots(3,5,','plt.subplots(len(places),5,squeeze=False,')
    text=text.replace('figsize=(21,12)','figsize=(21,4*len(places))')
    tree=ast.parse(text)
    if site!='B173nb_b10':
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='draw_remaining')
        start=next(i for i,n in enumerate(node.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='row' for t in n.targets))
        stop=next(i for i,n in enumerate(node.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ctx' for t in n.targets))
        del node.body[start:stop]
    class Labels(ast.NodeTransformer):
        def visit_keyword(self,node):
            if node.arg=='provisional':node.value=ast.Constant(False)
            return self.generic_visit(node)
    tree=ast.fix_missing_locations(Labels().visit(tree));figs=types.ModuleType('finaltrain_rescore_figures');figs.__file__=str(path)
    exec(compile(tree,str(path),'exec'),figs.__dict__);figs.SITE=site;figs.FINAL_TARGET=O/'targets'/f'{stem}.npz'
    source_values=figs.value;pending=[]
    def value(p,f,m):
        vp=root/'scores'/figs.key(p,f,m)/'values.json'
        if vp.exists():
            v=source_values(p,f,m)
            if f!='method' and v['mesh'].startswith('/out/'):v['mesh']=str(RS/v['mesh'][5:])
            return v
        if f not in pending:pending.append(f)
        nan=float('nan');return dict(key=figs.key(p,f,m),scene=dict(completeness=nan,accuracy=nan),
            cells=[dict(cell=i,completeness=nan,accuracy=nan,gt_mean_m=nan,result_mean_m=nan,n_gt=None,n_result=None) for i in [0,1,2,3,4]],status='셈 전')
    figs.value=value
    def artifact(fig,name,meta):
        # Pending rows are absent observations, never numeric zero.
        for obj in fig.findobj():
            if hasattr(obj,'get_text') and hasattr(obj,'set_text'):
                label=obj.get_text()
                if isinstance(label,str) and 'nan' in label:obj.set_text(label.replace('nan%','셈 전').replace('nancm','셈 전').replace('nan','셈 전'))
        meta.update(site=site,prior=prior,method=method,provisional=False,source_script=str(path),source_script_sha256=sha(path),
            target_sha256=sha(figs.FINAL_TARGET),places_sha256=sha(mod.C/'representatives_v1.json'),pending_families=pending,
            adaptations=['output/input roots','method name','actual FINALTRAIN sigma','explicit missing comparison panels','inherited per-site representative count'])
        out=D/'figures';out.mkdir(exist_ok=True);name=stem+'_'+name
        fig.savefig(out/(name+'.png'),dpi=300,facecolor='white');figs.plt.close(fig)
        dump(out/(name+'.json'),clean(dict(meta,colors=figs.COL,dpi=300,scientific_verdict=None)))
    figs.artifact=artifact
    cache=root/'figure_cache'/prior/method
    if not (cache/'receipt.json').exists():
        start=time.monotonic();ctx=figs.context(site,prior);gt=ctx['gt'].Gb
        box=np.asarray(json.loads((O/'meshes'/stem/'final_work/inputs/meta.json').read_text())['box'])
        frames={'all':figs.frame(box)};frames.update({r['id']:figs.frame(figs.roi_box(r,gt),650,500) for r in places['rows']});cache.mkdir(parents=True,exist_ok=True)
        dump(cache/'frames.json',{k:figs.serial_frame(v) for k,v in frames.items()})
        for family in ['prior','mvs','fusion','method','baseline_30000']:
            v=value(prior,family,method);data={}
            if v.get('status')=='셈 전':
                for name,f in frames.items():
                    keys=['all_gt','all_result'] if name=='all' else [name+'_image']
                    for key in keys:data[key]=np.ones((f['H'],f['W'],3))
                    if name!='all':data[name+'_section']=np.empty((0,2,2))
            else:
                points=loadz(root/'scores'/v['key']/'points.npz',['scene_distance_m','scene_tau_m']);V,F=figs.read_surface(v['mesh']);scene=figs.MeshScene(V,F)
                data['all_gt']=figs.gt_image(gt,points['scene_distance_m'],points['scene_tau_m'],frames['all']);data['all_result']=figs.render_mesh(scene,ctx,frames['all'],cache/(family+'_all_columns'))
                for row in places['rows']:
                    im=figs.render_mesh(scene,ctx,frames[row['id']],cache/(family+'_'+row['id']+'_columns'))
                    data[row['id']+'_image']=figs.gt_image(gt,points['scene_distance_m'],points['scene_tau_m'],frames[row['id']],im,True)
                    data[row['id']+'_section']=figs.section_segments(V,F,row)
                del V,F,scene;gc.collect()
            savez(cache/(family+'.npz'),**data);print('FIGURE_CACHE',stem,family,flush=True)
        savez(cache/'reference.npz',**{r['id']+'_gt':figs.section_points(gt,r) for r in places['rows']})
        dump(cache/'receipt.json',dict(at=now(),status='PASS',seconds=time.monotonic()-start,pending_families=pending,source_sha256=sha(path),scientific_verdict=None))
    else:pending.extend(json.loads((cache/'receipt.json').read_text()).get('pending_families',[]))
    if mode=='early':figs.draw_early(prior,method)
    elif mode=='remaining':
        figs.draw_remaining(prior,method)
        if site!='B173nb_b10':dump(D/'figures'/f'{stem}_figure7_6_scope.json',dict(status='NOT_APPLICABLE_B173_SKYLIGHT',reason='The fixed B skylight of figure 7.6 lies in B173. Regional figures 7.3/7.4/7.5/7.7 use the corresponding region and inherited sections.',scientific_verdict=None))
    else:raise ValueError(mode)
    print('FIGURES_DONE',stem,mode,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
