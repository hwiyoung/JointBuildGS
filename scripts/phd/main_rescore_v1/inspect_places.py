from common import *
site='B173nb_b10';p=PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1/work/places.npz';z=loadz(p);print('PLACE_KEYS',[(k,list(v.shape)) for k,v in z.items() if any(x in k for x in ['glass_strip','flat_roof'])])
for prior in ['ALS','LoD2']:
 d=loadz(JA/'core_points'/f'{site}__{prior}.npz',['source_index','centre','area','kind','building']);v=loadz(CELLS/f'{site}__{prior}.npz',['cell_v2']);full=loadz(TG/'stage0_r1/inputs'/f'{site}_{prior}.npz',['centre'])
 for label in ['glass_strip','flat_roof']:
  ids=z[label+'__'+prior];P=full['centre'][ids];ix=np.isin(d['source_index'],ids)
  print(prior,label,'centre',np.median(P,axis=0),'min',P.min(0),'max',P.max(0),'counts',np.unique(v['cell_v2'][ix],return_counts=True),'buildings',np.unique(d['building'][ix]))
