"""Replace the keep bar chart with an actual-coordinate binned section."""
from common import *
from PIL import Image, ImageDraw
import layout_revision_02 as L
import semantic_revision_03 as S
import presentation_revision_06 as R6

OUT=DOC/'revision_07';FIG=OUT/'figures';CACHE=PAY/'revision_07'

def section():
    c=load(CFG/'keep_shape_revision_07.json');source=PAY/c['source_cloud'];vp=DOC/c['source_view_metadata']
    assert sha(source)==c['source_cloud_sha256'];assert sha(vp)==c['source_view_metadata_sha256']
    v=load(vp);assert v['component_id']==c['component_id'];component=load(DOC/'figures/task0_specular_candidates.json')['selected'];mid=np.asarray(v['view']['centre']);e1=np.asarray(v['view']['axis1']);normals=np.asarray(component['normal']);e2=np.median(normals,axis=0);e2/=np.linalg.norm(e2);cross=np.cross(e1,e2)
    assert np.allclose(normals,e2), 'A single normal-axis tolerance requires a planar selected component'
    assert np.allclose(np.stack([e1,e2,cross])@np.stack([e1,e2,cross]).T,np.eye(3))
    edges=np.arange(c['along_section_limits_m'][0],c['along_section_limits_m'][1]+c['bin_width_m']/2,c['bin_width_m']);centres=(edges[:-1]+edges[1:])/2;series={};width_audit=[]
    with np.load(source) as z:
        for half_width in c['section_half_width_candidates_m']:
            counts={}
            for key in ['gt','prior','mvs']:
                q=z[key]-mid;x=q@e1;t=q@cross;keep=(abs(t)<=half_width)&(x>=edges[0])&(x<=edges[-1]);bins=np.minimum(np.floor((x[keep]-edges[0])/c['bin_width_m']).astype(int),len(centres)-1);counts[key]=np.bincount(bins,minlength=len(centres))
            complete=all(np.all(n>=c['minimum_points_per_source_per_bin']) for n in counts.values());width_audit.append(dict(half_width_m=half_width,counts=counts,all_bins_supported=bool(complete)))
            if complete:break
        for key in ['gt','prior','mvs']:
            q=z[key]-mid;uv=np.c_[q@e1,q@e2];t=q@cross;keep=(abs(t)<=half_width)&(uv[:,0]>=edges[0])&(uv[:,0]<=edges[-1]);ids=np.flatnonzero(keep);selected=uv[keep];bins=np.minimum(np.floor((selected[:,0]-edges[0])/c['bin_width_m']).astype(int),len(centres)-1)
            median=np.full(len(centres),np.nan);count=np.zeros(len(centres),int);minimum=median.copy();maximum=median.copy()
            for b in range(len(centres)):
                values=selected[bins==b,1];count[b]=len(values)
                if len(values)>=c['minimum_points_per_source_per_bin']:median[b]=np.median(values);minimum[b]=values.min();maximum[b]=values.max()
            series[key]=dict(source_point_count=len(q),section_point_count=len(ids),point_indices=ids,projected_points=selected,counts=count,median=median,minimum=minimum,maximum=maximum)
        prior_residual=(z['prior']-z['gt'])@e2
    basis=dict(centre=mid,axis1=e1,axis2=e2,rule='Exact original component normal, no tilted projection; separation is normal-direction distance')
    profile=dict(task_id=c['task_id'],scientific_verdict=None,config=c,config_sha256=sha(CFG/'keep_shape_revision_07.json'),source_view=basis,previous_tilted_view=v['view'],cross_axis=cross,edges_m=edges,bin_centres_m=centres,series=series,section_half_width_m=half_width,width_support_audit=width_audit,tau_m=component['tau_m'],normal_and_tau_source_sha256=sha(DOC/'figures/task0_specular_candidates.json'),local_paired_prior_audit=dict(points=len(prior_residual),signed_min_m=float(prior_residual.min()),signed_max_m=float(prior_residual.max()),absolute_median_m=float(np.median(abs(prior_residual))),within_tau_share=float(np.mean(abs(prior_residual)<=component['tau_m'])),scope='All 241 matched prior/reference points in the original local input cloud; not the entire selected building'),
        statistic='Actual-coordinate median per fixed 0.5 m bin; section width determined by point support alone, no fitted line and no shifted profile',
        limitations='MVS points pool the existing views; unequal per-bin density and outliers remain in the source record. Median profile is not a physical continuous surface or independent truth validation. Full-component 12/34 cm bar values do not describe this local section.')
    dump(OUT/'keep_section.json',profile);return profile

def draw_plot(profile):
    plt=plot_setup(50);fig=plt.figure(figsize=(10.8,5.2),dpi=100);ax=fig.add_axes([.05,.22,.90,.60]);x=np.asarray(profile['bin_centres_m']);gt=np.asarray(profile['series']['gt']['median']);tau=profile['tau_m'];all_values=list(np.r_[gt-tau,gt+tau]);ax.fill_between(x,gt-tau,gt+tau,color='#E1E6EB',zorder=0)
    for key,col in [('prior',S.PRIOR),('mvs',S.MVS),('gt',S.GT)]:
        y=np.asarray(profile['series'][key]['median']);all_values.extend(y[np.isfinite(y)])
        if key=='gt':ax.scatter(x,y,c=col,s=65,zorder=4)
        else:ax.plot(x,y,c=col,lw=5 if key=='prior' else 4,ls='--' if key=='prior' else '-',marker='o' if key=='prior' else None,markersize=3,zorder=3 if key=='prior' else 2)
    lo,hi=min(all_values),max(all_values);pad=max((hi-lo)*.10,.04);ax.set_xlim(-3,3);ax.set_ylim(lo-pad,hi+pad);ax.axis('off')
    for x,label,col in [(.02,'참값',S.GT),(.31,'사전 정보',S.PRIOR),(.78,'영상',S.MVS)]:fig.text(x,.98,label,color=col,fontsize=50,va='top')
    fig.text(.5,.025,'회색: 허용 ±20 cm',color='#526373',fontsize=50,ha='center',va='bottom')
    path=CACHE/'keep_shape.png';fig.savefig(path,dpi=100,facecolor='white');plt.close(fig)
    profile['display']=dict(y_limits_m=[lo-pad,hi+pad],normal_separation_exaggerated=True,all_nonempty_bin_medians_visible=True,reference_band_m=tau,reference_band_semantics='Existing normal-direction tolerance around the binned reference profile; not a statistical confidence band',palette='Same as R6 correct/refine cards',comparison_raster_sha256=sha(path));dump(OUT/'keep_section.json',profile);return Image.open(path)

def draw_photo(profile):
    old=load(DOC/'revision_06/figures/figS_e_aim_keep.json');pm=dict(old['photo']);p=pm['source']['photo'];crop=pm['crop_in_rotated_native_px'];im=L.native(p);rot=pm['display_rotation_deg']
    if rot==90:im=im.transpose(Image.Transpose.ROTATE_90)
    pic=im.crop(crop).resize((1080,600),Image.Resampling.LANCZOS);v=profile['source_view'];X=np.asarray(v['centre'])+np.linspace(-3,3,61)[:,None]*np.asarray(v['axis1'])
    pose=dict(p['pose'],R=np.asarray(p['pose']['R']),t=np.asarray(p['pose']['t']));q,_=G.project(X,pose,p['camera'])
    if rot==90:q=np.c_[q[:,1],p['camera']['w']-q[:,0]]
    q=(q-crop[:2])*[1080/(crop[2]-crop[0]),600/(crop[3]-crop[1])];R6.thin_line(pic,q);d=ImageDraw.Draw(pic)
    direction=q[-1]-q[0];direction/=np.linalg.norm(direction)
    for pt,label,sign in [(q[0],'A',-1),(q[-1],'A′',1)]:
        d.ellipse((pt[0]-10,pt[1]-10,pt[0]+10,pt[1]+10),fill='#FFD60A',outline=S.INK,width=3)
        pos=np.clip(pt+direction*sign*72+[-22,-40],[20,20],[980,500]);R6.label(pic,label,tuple(pos),68)
    R6.label(pic,'A–A′: 아래 단면의 위치',(26,510),68)
    pm.update(old_patch_hull_drawn=False,annotation='Centre line of the documented geometric section, not a building boundary',section_centre_line_xyz=X.tolist(),section_line_display_px=q.tolist(),section_half_width_m=profile['section_half_width_m'])
    return pic,pm,old

def main():
    config();OUT.mkdir(exist_ok=True);FIG.mkdir(exist_ok=True);CACHE.mkdir(exist_ok=True);profile=section();plot=draw_plot(profile);pic,pm,old=draw_photo(profile)
    card=Image.new('RGB',(1080,1620),'white');ImageDraw.Draw(card).line((28,3,1052,3),fill=S.INK,width=7);L.text(card,(28,28),'보존',94,bold=True);card.paste(pic,(0,160));L.text(card,(28,790),'A–A′ 단면 · 면 차이 확대',68);card.paste(plot,(0,890))
    explanation=['허용 범위의 사전 정보는','영상이 틀려도 지킨다'];L.text(card,(28,1430),explanation[0],70);L.text(card,(28,1530),explanation[1],70,col=S.PROP)
    name='figS_e_aim_keep';card.save(FIG/f'{name}.png');dump(FIG/f'{name}.json',dict(task_id=profile['task_id'],scientific_verdict=None,photo=pm,comparison=profile,explanation=explanation,minimum_font_px=68,slide_card_size=[400,600],purpose_not_success_claim=True,source_component_unchanged=True))
    combined=Image.open(DOC/'revision_06/figures/figS_e_purpose_overview.png').convert('RGB');combined.paste(card,(0,0));ImageDraw.Draw(combined).line((1080,0,1080,1620),fill='#DFE5EA',width=2);name='figS_e_purpose_overview';combined.save(FIG/f'{name}.png');dump(FIG/f'{name}.json',dict(task_id=profile['task_id'],scientific_verdict=None,cards=['keep','correct','refine','inherit'],changed_card='keep',other_cards='R6 PNG bytes retained',minimum_font_px=68,slide_size=[1600,600]))
    preview=OUT/'previews';preview.mkdir(exist_ok=True);card.resize((400,600),Image.Resampling.LANCZOS).save(preview/'figS_e_aim_keep.png');combined.resize((1600,600),Image.Resampling.LANCZOS).save(preview/'figS_e_purpose_overview.png')
    print('R7',[(k,v['section_point_count'],v['counts'].tolist(),v['median'].tolist()) for k,v in profile['series'].items()],flush=True)

if __name__=='__main__':main()
