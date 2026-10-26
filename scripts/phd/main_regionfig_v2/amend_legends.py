from rfcore import *
import shutil

cfg=load(CFG/'regionfig_v2.json');files=[]
for i in ['5','6']:
    src=DOC/f'figures/검토용_{i}_제목숨김.png';dst=DOC/f'reviews/검토용_{i}_범례보완전.png';dst.parent.mkdir(parents=True,exist_ok=True);assert not dst.exists();shutil.copy2(src,dst)
    files.append(dict(id=i,path=str(dst),sha256=sha(dst),reviewed_before_legend_clarification=True))
dump(DOC/'reviews/reviewed_images.json',files)
for ex in cfg['examples']:
    path=PAY/f'section_{ex["id"]}.json';before=load(path);after=sections(ex,data(ex['prior'],ex['building']))
    assert np.allclose(np.array(before['heights_model_m'],float),np.array(after['heights_model_m'],float),equal_nan=True)
    dump(path,after)
dump(CFG/'amendment_02_legends.json',dict(at=now(),scientific_verdict=None,
    reason='Independent viewers could locate result errors but the region names alone did not consistently communicate prior correctness. Explicitly define refinement/correction/preservation in the legend. Add required black hatching to inherited-wrong section bins.',
    changes='Legend labels only; section hatch when inherited-wrong area is at least half of the dominant inherited region in the bin.',
    original_config_sha256=sha(CFG/'regionfig_v2.json'),changes_values=False,changes_photo=False,changes_crop=False,changes_opacity=False,
    reviewed_images=files,before_revised_render=True))
dump(CFG/'amendment_02_legends.lock.json',dict(at=now(),sha256=sha(CFG/'amendment_02_legends.json'),scientific_verdict=None))
print('legend and hatch amendment locked',environment())
