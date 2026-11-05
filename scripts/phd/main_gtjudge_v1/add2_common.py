from common import *
import numpy as np

def config2():
    v=json.loads((C/'addendum2.json').read_text());lock=json.loads((C/'addendum2.lock.json').read_text())
    assert sha(C/'addendum2.json')==lock['config_sha256']
    return v

def target_file(site,prior,variant=None):
    if prior=='ALS' or variant=='alt_ga':return FT/'targets'/f'{site}__{prior}.npz'
    if variant is None:variant=json.loads((D/'판고르기.json').read_text())['selected']
    if variant=='alt_ga':return FT/'targets'/f'{site}__{prior}.npz'
    return O/'targets_alt'/variant/f'{site}__{prior}.npz'

def full_owner(site,prior):
    stem=f'{site}__{prior}';row=loadz(O/'scenes'/stem/'rows.npz');core=loadz(JA/'core_points'/f'{stem}.npz',['source_index'])
    owner=row['row_owner'];out=np.full(len(owner),-1,'i8');good=owner>=0;out[good]=core['source_index'][owner[good]]
    return row,out

def target_membership_rows(site,prior,mask):
    row,owner=full_owner(site,prior);good=owner>=0;inside=np.zeros(len(owner),bool);inside[good]=mask[owner[good]]
    labels=loadz(O/'scenes'/f'{site}__{prior}'/'stage1_cells.npz',['case_id'])['case_id']
    return [dict(case_id=int(k),n_gt=int((inside&(labels==k)).sum())) for k in [0,1,2,4,3,-1]]
