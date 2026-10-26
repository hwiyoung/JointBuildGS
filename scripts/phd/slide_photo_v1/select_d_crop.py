from common import *
config();assert (CFG/'amendment_01_d_crop.json').exists();rows=[]
with np.load(U/'patch_values/B0_b10__LoD2__R1.5.npz') as z:evalmask=z['in_eval'];centres=z['centre'][evalmask]
from task0_scan import cameras_depth
_,cam=cameras_depth();poses=G.poses(G.DENSE/'triangulated/images.bin')
am=CFG/'amendment_02_d_full_roi.json'
if not am.exists():dump(am,dict(at=now(),before_first_render=True,reason='A six-by-four pixel edge fragment is not the requested B0 view. Require the full B0 input footprint to be in frame before applying the approved crop and mask ranking.',minimum_projected_patch_fraction=.95,scientific_verdict=None))
for name in load(S0/'fork_inputs/s61/B0_b10/split.json')['train']:
    stem=Path(name).stem;ex=S0/'s61/export/B0_b10/LoD2';lm=np.load(ex/'locmap'/f'{stem}.npy');roi=np.zeros_like(lm,bool);hit=lm>=0;roi[hit]=evalmask[lm[hit].astype(int)]
    y,x=np.nonzero(roi)
    if not len(x):continue
    box=[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)];share=len(x)/((box[2]-box[0])*(box[3]-box[1]))
    if share<=.5:continue
    uv,zz=G.project(centres,poses[stem],cam);fraction=float(((zz>0)&(uv[:,0]>=0)&(uv[:,0]<1024)&(uv[:,1]>=0)&(uv[:,1]<741)).mean())
    if fraction<.95:continue
    D=np.load(ex/'mvs'/f'{stem}.npy');cf=np.load(ex/'conf'/f'{stem}.npy');passed=np.isfinite(D)&(D>0)&(cf>0)
    rows.append(dict(view=stem,crop_box_grid_px=box,eval_crop_share=share,projected_eval_patch_fraction=fraction,roi_pixels=len(x),pass_share=float(passed[roi].mean())))
rows.sort(key=lambda r:(-r['pass_share'],-r['roi_pixels'],r['view']))
dump(PAY/'selection_d_crop.json',dict(selected=rows[0] if rows else None,candidates=rows,scientific_verdict=None));print(rows[:1])
