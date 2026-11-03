"""Render one real development roof background before photo census completion."""
import sys
import numpy as np
from figures_reply2 import BASE,O,loadz,background,Cameras,plt,dump,now

def main(prior='ALS'):
    files=sorted((O/'r1/geometry').glob(f'*__{prior}.npz'))
    parts=[];tiles=[]
    for path in files:
        source=loadz(path);keep=source['kind']==1
        parts.append({k:source[k][keep] for k in ['patch_id','building','centre','area','geometry']})
        tiles.append(np.full(int(keep.sum()),path.stem.split('__')[0]))
    data={k:np.concatenate([part[k] for part in parts]) for k in parts[0]}
    data['tile']=np.concatenate(tiles)
    ranking=sorted([(float(data['area'][(data['building']==bid)&(data['geometry']==1)].sum()),str(bid)) for bid in np.unique(data['building'])],key=lambda x:(-x[0],x[1]))
    area,bid=ranking[0];keep=data['building']==bid;selected={k:v[keep] for k,v in data.items()}
    cameras=Cameras();pixels,extent,camera,metadata=background(selected,cameras,prior)
    dest=BASE/'visual_preflight'/f'background_{prior}_{bid}';dest.parent.mkdir(parents=True,exist_ok=True)
    fig,ax=plt.subplots(figsize=(7,7));ax.imshow(pixels,origin='lower',extent=extent);ax.set_aspect('equal');ax.set_title(f'{prior} · 개발용 지붕 지도 바탕 검사');ax.set_xticks([]);ax.set_yticks([])
    fig.tight_layout();fig.savefig(dest.with_suffix('.png'),dpi=150);plt.close(fig)
    dump(dest.with_suffix('.json'),dict(at=now(),building=bid,prior=prior,selection='largest retained development roof outside-limit area; ID tie break',outside_area_m2=area,background=metadata,camera=cameras.names[camera] if camera is not None else None,patch_ids=selected['patch_id'].tolist(),photo_judgments_used=False,reference_values_used=False,delivery_figure=False,scientific_verdict=None))
    print('BACKGROUND_PREFLIGHT',str(dest.with_suffix('.png')),flush=True)

if __name__=='__main__':main(*sys.argv[1:])
