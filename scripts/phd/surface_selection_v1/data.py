"""Immutable full-stage viewer data; exact original RGB and sampled native rows."""
from collections import OrderedDict
import colorsys
import json
from pathlib import Path
import cv2
import numpy as np
from scripts.phd.surface_selection_v1.common import verify_seal,sha,clean
from src.phd.surface_selection_v1.units import unit_candidates
from src.phd.surface_selection_v1.evidence import replay_evidence
from src.phd.source_candidate_v1.geometry import self_depth_buffer

def read(p):return json.loads(Path(p).read_text())

class Store:
    def __init__(self,root='/output/run',inputs='/inputs'):
        if Path('/reference').exists():raise ValueError('Raw reference forbidden in viewer')
        self.root=Path(root);self.inputs=Path(inputs)
        self.config,self.seal,self.seal_sha=verify_seal(self.root)
        for p,digest in self.seal['replay_module_sha256'].items():
            if sha(p)!=digest:raise ValueError('Replay implementation differs from frozen method: '+p)
        self.regions={};self.native={};self.members={};self.views={};self.images={};self.replay_cache=OrderedDict();self.context_cache=OrderedDict()
        # Evaluation schema is checked by receipt; no raw UAS is mounted.
        receipt_path=self.root/'evaluation/evaluation_receipt.json'
        if (self.root/'evaluation').exists() and not receipt_path.is_file():raise ValueError('Incomplete evaluation receipt')
        if receipt_path.exists():
            receipt=read(receipt_path)
            if (receipt.get('method_seal_sha256')!=self.seal_sha or receipt.get('scientific_verdict') is not None
                or receipt.get('reference_accessed_only_after_all_method_verification') is not True
                or not {'summary.json','per_unit.json'}<=set(receipt.get('output_sha256',{}))):raise ValueError('Evaluation provenance mismatch')
            for rel,digest in receipt.get('output_sha256',{}).items():
                p=Path(rel)
                if p.is_absolute() or '..' in p.parts or sha(self.root/'evaluation'/p)!=digest:raise ValueError('Evaluation changed')
        self.eval_summary=read(self.root/'evaluation/summary.json') if receipt_path.exists() else {}
        evalrows=read(self.root/'evaluation/per_unit.json') if receipt_path.exists() else []
        self.evaluations={}
        if isinstance(evalrows,list):
            for row in evalrows:self.evaluations[(row.get('region'),int(row.get('unit_id',row.get('id',-1))))]=row
        elif isinstance(evalrows,dict):
            for region,rows in evalrows.items():
                if isinstance(rows,list):
                    for row in rows:self.evaluations[(region,int(row.get('unit_id',row.get('id',-1))))]=row
        verified=set()
        for region,spec in self.config['regions'].items():
            r=self.root/region
            for name,key in (('native.npz','native_sha256'),('views.json','views_sha256')):
                if sha(self.inputs/region/name)!=spec[key]:raise ValueError('Native input changed')
            with np.load(self.inputs/region/'native.npz',allow_pickle=False) as z:self.native[region]={k:z[k] for k in z.files}
            with np.load(r/'membership.npz',allow_pickle=False) as z:self.members[region]={k:z[k] for k in z.files}
            self.views[region]={};self.images[region]={}
            for v in read(self.inputs/region/'views.json')['views']:
                path=Path(v['path'])
                if str(path) not in verified:
                    if sha(path)!=v['sha256']:raise ValueError('Original RGB changed')
                    verified.add(str(path))
                R=np.array(v['R']);t=np.array(v['t'])
                self.views[region][str(v['image_id'])]=dict(id=v['image_id'],name=v['name'],path=str(path),R=R,t=t,K=np.array(v['K']),center=-R.T@t,
                    width=v['width'],height=v['height'],image_url=f"/images/{region}/{v['image_id']}")
                self.images[region][str(v['image_id'])]=path
            units=read(r/'units.json');obs=read(r/'observations.json');decs=read(r/'decisions.json')
            if len(units)!=len(obs) or len(obs)!=len(decs):raise ValueError('Unit census mismatch')
            for u,o,d in zip(units,obs,decs):
                if u['id']!=o['unit_id'] or u['id']!=d['unit_id']:raise ValueError('Unit identity mismatch')
                u['decision']=d
                u['observation']={'shared':{k:v for k,v in o['observation']['shared'].items() if k!='selected_pairs'},
                                  'status':o['observation']['status']}
            self.regions[region]=dict(id=region,domain=spec['domain'],components=read(r/'components.json'),graphs=read(r/'graphs.json'),
                units=units,unit_graph=read(r/'unit_graph.json'),summary=dict(input=read(r/'input_summary.json'),decision=read(r/'summary.json'),
                    evaluation=self.eval_summary.get('regions',{}).get(region,{})),observations=obs)
        self.verified_images=len(verified)

    def manifest(self):
        return dict(task_id=self.config['task_id'],method_seal_sha256=self.seal_sha,scientific_verdict=None,verified_image_count=self.verified_images,
            regions=[dict(id=r,summary=d['summary'],default_unit_id=self.default_unit(r)) for r,d in self.regions.items()])

    def default_unit(self,region):
        d=self.regions[region];units=d['units']
        candidates=[u for u in units if u['decision']['action']!='ABSTAIN']
        if not candidates:candidates=[u for u,o in zip(units,d['observations']) if o['observation']['status']=='SCORED']
        return max(candidates or units,key=lambda u:(u['area_m2'],-u['id']))['id']

    def region(self,region):return {k:v for k,v in self.regions[region].items() if k!='observations'}

    def unit(self,region,uid):
        i=int(uid);d=self.regions[region]
        if i<0 or i>=len(d['units']):raise KeyError(uid)
        return dict(region=region,unit=d['units'][i],observation=d['observations'][i]['observation'],decision=d['units'][i]['decision'],
            evaluation=self.evaluations.get((region,i)),scientific_verdict=None)

    def points(self,region,source):
        if source not in ('mvs','als'):raise KeyError(source)
        n=self.native[region];m=self.members[region];xyz=n[source+'_xyz'];cap=self.config['viewer']['display_cap_per_source']
        rows=np.linspace(0,len(xyz)-1,min(len(xyz),cap),dtype=int)
        rgb=n.get(source+'_rgb')
        if rgb is None:rgb=np.tile(np.array([255,162,64] if source=='als' else [73,171,225]),(len(xyz),1))
        if rgb.size and np.max(rgb)<=1.:rgb=np.asarray(rgb)*255
        return dict(positions=xyz[rows].ravel().tolist(),colors=np.asarray(rgb)[rows,:3].astype(int).ravel().tolist(),
            component_ids=m[source+'_component'][rows].tolist(),unit_ids=m[source+'_unit'][rows].tolist(),
            native_row_indices=rows.tolist(),native_count=len(xyz),display_count=len(rows),display_only=True)

    def image_path(self,region,imageid):return self.images[region][str(imageid)]

    def _view_context(self,region,ids):
        views=[];contexts={s:{} for s in ('mvs','als')}
        for vi in ids:
            key=(region,str(vi))
            if key not in self.context_cache:
                v=dict(self.views[region][str(vi)]);v['gray']=cv2.imread(v['path'],cv2.IMREAD_GRAYSCALE).astype(np.float32)
                c={s:self_depth_buffer(self.native[region][s+'_xyz'],v,**self.config['self_visibility']) for s in contexts}
                self.context_cache[key]=(v,c)
                while len(self.context_cache)>8:self.context_cache.popitem(last=False)
            v,c=self.context_cache[key];self.context_cache.move_to_end(key);views.append(v)
            for s in contexts:contexts[s][v['id']]=c[s]
        return views,contexts

    def evidence(self,region,uid,pair_id=None,anchor=None):
        key=(region,int(uid),pair_id,anchor)
        if key in self.replay_cache:self.replay_cache.move_to_end(key);return self.replay_cache[key]
        item=self.unit(region,uid);obs=item['observation'];pairs=obs['shared']['selected_pairs']
        def scored(p):return any(v is not None for v in [*p.get('own_costs',{}).values(),*p.get('paired_costs',{}).values()])
        valid_patches=[p for p in obs['patches'] if scored(p)]
        scored_ids={p['pair_id'] for p in valid_patches}
        available=[dict(p,pair_id=p['pair_id'],scored=p['pair_id'] in scored_ids) for p in pairs]
        if not pairs:return dict(available=False,reason='현재 관측 영상쌍이 없습니다.',region=region,unit_id=int(uid),pairs=[],scientific_verdict=None)
        pair=next((p for p in pairs if p['pair_id']==pair_id),None) if pair_id is not None else next((p for p in pairs if p['pair_id'] in scored_ids),None)
        if pair_id is None and pair is None:return dict(available=False,reason='저장 영상쌍에서 유효한 관측 패치를 얻지 못했습니다.',region=region,unit_id=int(uid),pairs=available,scientific_verdict=None)
        if pair is None:raise KeyError('Unknown scored pair')
        patch_rows=[p for p in valid_patches if p['pair_id']==pair['pair_id']]
        if not patch_rows:return dict(available=False,reason='이 영상쌍에 유효한 관측 패치가 없습니다.',region=region,unit_id=int(uid),pairs=available,scientific_verdict=None)
        if anchor is None:
            selected=max(patch_rows,key=lambda p:(sum(v is not None for v in p.get('paired_costs',{}).values()),p.get('common_pixels',0),-p['patch_index']))
            anchor=selected['patch_index']
        else:
            selected=next((p for p in patch_rows if p['patch_index']==anchor),None)
            if selected is None:raise ValueError('This patch has no finite saved observation')
        views,contexts=self._view_context(region,[pair['reference_id'],pair['target_id']])
        m=self.members[region]
        candidates=unit_candidates(item['unit'],self.native[region],{s:m[s+'_component'] for s in contexts},m,self.regions[region]['components'],contexts)
        result=replay_evidence(obs,candidates,views,pair['pair_id'],anchor)
        result.update(region=region,pairs=available,anchor=result.get('anchor_index'),
            anchor_count=len(pair['anchor_ids']),anchor_indices_valid=[p['patch_index'] for p in patch_rows],
            profile={s:obs['candidates'][s]['profile'] for s in contexts},reproduction_tolerance=1e-6)
        for source,reproduced in result.get('reproduced_pair_costs',{}).items():
            saved=next((r['cost'] for r in obs['candidates'][source]['pairs'] if r['pair_id']==pair['pair_id']),None)
            if (saved is None)!=(reproduced is None) or (saved is not None and abs(saved-reproduced)>1e-6):raise ValueError('Saved pair cost did not reproduce')
        for field in ('costs','own_costs'):
            for source in ('mvs','als'):
                saved=selected.get('paired_costs' if field=='costs' else field,{}).get(source);actual=result.get(field,{}).get(source)
                if (saved is None)!=(actual is None) or (saved is not None and abs(saved-actual)>1e-6):raise ValueError('Selected patch cost did not reproduce')
        common=all(result.get('costs',{}).get(s) is not None for s in ('mvs','als'))
        masks=result['own_masks'];union=np.logical_or.reduce([np.asarray(m,bool) for m in masks.values()]).tolist()
        result.update(comparison_mode='COMMON_MASK_COMPARISON' if common else 'INDEPENDENT_SOURCE_SUPPORT',reproduced=True,
            patch=dict(width=result['patch_width'],**result['patches'],mask=result['common_mask'] if common else union,
                       source_masks={s:result['common_mask'] if common else masks.get(s,[False]*result['patch_width']**2) for s in ('mvs','als')},
                       costs=result['costs'] if common else result['own_costs']))
        for side in ('reference','target'):result[side]['url']=result[side]['image_url']
        self.replay_cache[key]=clean(result)
        while len(self.replay_cache)>16:self.replay_cache.popitem(last=False)
        return self.replay_cache[key]
