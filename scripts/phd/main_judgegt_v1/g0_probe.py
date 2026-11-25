"""입력 열 모양 살피기 (읽기만)."""
import numpy as np, json, pandas as pd, glob
PH='/art/phase-payloads/phd'
for p in ['ALS','LoD2']:
    z=np.load(f'{PH}/main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1/patch_{p}.npz',mmap_mode='r')
    print(p,[(k,z[k].dtype.str,z[k].shape) for k in z.files])
    print(' tiles',z['tiles'][:30])
    t=pd.read_csv(f'{PH}/main_mvsfilter_v1/PHD-MAIN-MVSFILTER-v1/judge/patches4_{p}.csv.gz',usecols=['patch_index','patch_id','kind','area','initial_state','none_cyl_points','none_n','combo_D_judgment','building','region','place'])
    print(' csv rows',len(t),'npz rows',len(z['kind']),'idx==arange',bool((t.patch_index.values==np.arange(len(t))).all()))
    print(' kind eq',bool((t.kind.values==z['kind']).all()),'area eq',bool(np.allclose(t.area.values,z['area'])),'bld eq',bool((t.building.values==z['building']).all()))
    print(' initial_state',t.initial_state.value_counts().to_dict()); print(' combo_D',t.combo_D_judgment.value_counts().to_dict()); print(' place',t.place.value_counts().to_dict())
    print(' prior_h finite',np.isfinite(z['prior_height_m']).mean(),'LoD2 ph uniq' if p=='LoD2' else '',np.unique(z['prior_height_m'][np.isfinite(z['prior_height_m'])])[:3] if p=='LoD2' else '')
    print(' j_region shape',z['j_region'].shape, 'method col counts',np.unique(z['j_region'][:,4],return_counts=True))
    print(' place npz',np.unique(z['place'],return_counts=True))
    a=z['area']; print(' area q',np.quantile(a,[0,.5,1]))
for f in sorted(glob.glob(f'{PH}/main_widen0_v2/PHD-MAIN-WIDEN0-v2/holdout/internal/points/*/gt_xyz.npy'))[:24]:
    g=np.load(f,mmap_mode='r'); m=np.load(f.replace('gt_xyz','mvs_a_xyz'),mmap_mode='r'); print(f.split('/')[-2],g.shape,g.dtype,np.asarray(g[::1000]).min(0).round(1),np.asarray(g[::1000]).max(0).round(1),m.shape,np.asarray(m[::1000]).min(0).round(1),np.asarray(m[::1000]).max(0).round(1))
