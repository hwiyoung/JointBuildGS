"""The same row scorer, five cases and inherited four image/prior subdivisions."""
from add4_common import *
from normal_line import values

FAMILIES=['always_keep_mesh','always_keep_mesh_t010']
COMPARISONS=['prior','fusion','judgment_mesh','gt_judgment_mesh','FINALTRAIN_30000']
CASE_NAMES={0:'둘 다 맞음',1:'영상만 맞음',2:'사전 정보만 맞음',4:'영상 없음',3:'둘 다 틀림'}
DIV={1:'무늬 없음만',2:'가장자리만',3:'둘 다',0:'그 밖',-2:'무늬 확인 불가'}

def table_all():
    records=[];sources=[]
    for site in SITES:
        for prior in PRIORS:
            stem=f'{site}__{prior}';root=O/'scenes'/stem;row=loadz(root/'rows.npz');cells=loadz(root/'stage1_cells.npz');features=loadz(AW/'features'/f'{stem}.npz');quadrant=features['quadrant']
            sources.extend(proof(p) for p in [root/'rows.npz',root/'stage1_cells.npz',AW/'features'/f'{stem}.npz',AW/'features'/f'{stem}.json'])
            for method in COMPARISONS+FAMILIES:
                path=(AW/'keep_scores'/stem if method in FAMILIES else root/'distances')/f'{method}.npz';s=loadz(path,['row_s'])['row_s'];sources.append(proof(path))
                for k in CASE_NAMES:
                    cm=cells['case_id']==k
                    for div,name in list(DIV.items())+[('all','경우 전체')]:
                        mask=cm if div=='all' else cm&(quadrant==div);v=values(s[mask],row['row_tau_m'][mask]);n=int(mask.sum())
                        records.append(dict(site=site,prior=prior,case_id=k,case_name=CASE_NAMES[k],division=name,method=method,method_label='사전 정보(단계1 원래 면의 값)' if method=='prior' else method,
                            n_gt=n,small='적음' if n<1000 else '',completeness_pct=v['within_pct'],far_hit_pct=v['far_hit_pct'],no_surface_pct=v['no_surface_pct'],n_within_tau=int((np.isfinite(s[mask])&(abs(s[mask])<=row['row_tau_m'][mask])).sum()),n_far_hit=v['n_hit']-int((np.isfinite(s[mask])&(abs(s[mask])<=row['row_tau_m'][mask])).sum()),n_no_surface=n-v['n_hit'],
                            case_basis='stage1 normal_line',distance='inherited normal_line five origin rays',comparison_source='new diagnostic mesh score' if method in FAMILIES else 'saved stage1/2 row distances reaggregated; no distance recomputation',source_file=str(path)))
    # Every four-way subdivision plus the explicitly unavailable texture rows partitions its case.
    for site in SITES:
        for prior in PRIORS:
            for m in COMPARISONS+FAMILIES:
                for k in CASE_NAMES:
                    rr=[r for r in records if (r['site'],r['prior'],r['method'],r['case_id'])==(site,prior,m,k)];whole=next(r for r in rr if r['division']=='경우 전체')
                    for field in ['n_gt','n_within_tau','n_far_hit','n_no_surface']:assert sum(r[field] for r in rr if r['division']!='경우 전체')==whole[field]
    path=AT/'always_keep.csv'
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator='\n');writer.writeheader();writer.writerows(records)
    dump(AT/'always_keep.json',dict(rows=records,sources=sources,prior_value_definition='Reuse stage1 prior row_s measured against original prior surface, before patch rectangles and TSDF; no invented patch-height scalar metric',scientific_verdict=None))
    print('ADD4_KEEP_TABLE',len(records),flush=True)

def section(key):
    c=case(key);rec=getcase(c);s=rec['section'];root=root_of(c);stem=f"{c['site']}__{c['prior']}";row=loadz(root/'rows.npz');take=section_mask(row['xyz'],s);pts=section_points(row['xyz'],s);segs={};src=[]
    for m in ['prior']+FAMILIES:
        path=meshpath(c,m) if m=='prior' else O/'meshes'/(stem+'__'+m)/'final.ply';V,F=read_surface(path);seg=section_segments(V,F,s)
        for j in range(2):
            outside=(seg[:,j,0]<0)|(seg[:,j,0]>s['length_m'])
            if outside.any():
                x=np.clip(seg[outside,j,0],0,s['length_m']);a=seg[outside,j].copy();b=seg[outside,1-j].copy();t=(x-a[:,0])/(b[:,0]-a[:,0]);seg[outside,j]=a+t[:,None]*(b-a)
        segs[m]=seg;src.append(path);del V,F;gc.collect()
    lo=min([pts[:,1].min()]+[seg[:,:,1].min() for seg in segs.values() if len(seg)]);hi=max([pts[:,1].max()]+[seg[:,:,1].max() for seg in segs.values() if len(seg)]);pad=max(.1,(hi-lo)*.05);bounds=[0,s['length_m'],float(lo-pad),float(hi+pad)];W,H,S=1200,120,3;panels=[];rows=[]
    for m,col in zip(FAMILIES,['#4B3A99','#1D9E75']):
        im=Image.new('RGBA',(W*S,H*S));draw=ImageDraw.Draw(im)
        def px(q):q=np.asarray(q);return np.stack([q[...,0]/s['length_m']*W,(bounds[3]-q[...,1])/(bounds[3]-bounds[2])*H],-1)*S
        for name,color in [('prior',AC['method_colors']['prior']),(m,col)]:
            for edge in px(segs[name]):draw.line([tuple(x) for x in edge],fill=color,width=S)
        score=AW/'keep_scores'/stem/f'{m}.npz';v=loadz(score,['row_s'])['row_s'][take];colors=np.where(~np.isfinite(v),2,np.where(abs(v)<=row['row_tau_m'][take],0,1))
        for q,k in zip(px(pts),colors):draw.ellipse([q[0]-S*.85,q[1]-S*.85,q[0]+S*.85,q[1]+S*.85],fill=AC['gt_colors'][int(k)])
        if m==FAMILIES[0]:
            x,y=24*S,18*S;draw.line([(x,y),(x+2/s['length_m']*W*S,y)],fill='#16263D',width=2*S);draw.line([(x,y),(x,y+1/(bounds[3]-bounds[2])*H*S)],fill='#16263D',width=2*S)
        result=values(v,row['row_tau_m'][take]);im=im.resize((W,H),Image.Resampling.LANCZOS);panels.append(im);rows.append(dict(method=m,n_gt=len(pts),completeness_pct=result['within_pct'],metric_population='this 1m-wide section strip only',**result));src.append(score)
    merged=Image.new('RGBA',(W,H*2));merged.paste(panels[0],(0,0));merged.paste(panels[1],(0,H));y=(bounds[3]-rec['line_xyz'][0][2])/(bounds[3]-bounds[2])*H
    savepng(merged,AF/c['id']/'section_always_keep.png',dict(case=c['id'],section=s,rows=rows,axis_bounds=bounds,vertical_exaggeration=(H/(bounds[3]-bounds[2]))/(W/s['length_m']),A_px=[0,y],Aprime_px=[W,y],box_corners_px=[[0,0],[W,0],[W,H*2],[0,H*2]],scale_bar=dict(horizontal_m=2,vertical_m=1,horizontal_px=2/s['length_m']*W,vertical_px=1/(bounds[3]-bounds[2])*H),colors={'prior':AC['method_colors']['prior'],'always_keep_mesh':'#4B3A99','always_keep_mesh_t010':'#1D9E75'},producer=proof(__file__)),src+[root/'rows.npz'])
    print('ADD4_KEEP_SECTION',c['id'],flush=True)

if __name__=='__main__':
    table_all()
    for key in ['c1','c3']:section(key)
