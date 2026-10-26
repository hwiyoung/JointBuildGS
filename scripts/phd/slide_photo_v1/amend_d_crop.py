from common import *
c=config();p=CFG/'amendment_01_d_crop.json';assert not p.exists()
dump(p,dict(task_id=c['task_id'],at=now(),original_config_sha256=sha(CFG/'slide_photo_v1.json'),
 reason='No full-image view had B0 evaluation pixels >50%. User explicitly approved a common B0 crop for the five panels.',
 user_reply='네, B0를 크게 보여 주세요',selection='For each training view, tight bounding rectangle of B0 evaluation locmap pixels. Keep views with evaluation mask >50% of that crop. Choose highest MVS confidence-pass share over the ROI; ties largest projected ROI then view stem. Use exact same crop for all five images.',
 gaussian_closeup='Centre on input-selected B0 face 7 used for representation example, 3m square at face median. Show deterministic every-k Gaussian for legibility; not a statistical sample; projected actual scale and normal with display scale factor 0.25.',
 scientific_verdict=None))
print(sha(p))
