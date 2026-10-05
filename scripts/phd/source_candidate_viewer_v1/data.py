"""Read-only, provenance-checked stage-viewer data and exact patch replay.

Only native source arrays, original RGB, and sealed evaluation summaries are read.
Display sampling never enters scoring. No UAS geometry is mounted or loaded.
"""
from __future__ import annotations

from collections import OrderedDict
import json
from pathlib import Path
import threading

import cv2
import numpy as np

from scripts.phd.source_candidate_v1.common import clean, sha
from scripts.phd.source_candidate_v1.evaluate import verify_method_seal
from src.phd.source_candidate_v1.geometry import self_depth_buffer
from src.phd.source_candidate_v1.photometry import (
    ScoringConfig, _prepare_candidate, _patch_pixels, _sample_gray, _warp,
    _cost, _intersect, project,
)

TASK_ID = 'PHD-SOURCE-CANDIDATE-P1P2P3-v1'
DEFAULT_CELLS = {'P1': 16, 'P2': 5, 'P3': 43}
DISPLAY_CAP = 60000


def _read(path):
    return json.loads(Path(path).read_text())


def _finite(value):
    return value is not None and np.isfinite(value)


def _verify_files(root, files):
    for relative, digest in files.items():
        name = Path(relative)
        if name.is_absolute() or '..' in name.parts or sha(Path(root)/name) != digest:
            raise ValueError('Frozen viewer input changed: ' + str(relative))


def _remember(cache, key, value, maximum):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > maximum:
        cache.popitem(last=False)
    return value


class DataStore:
    """One immutable run, original image whitelist, and bounded replay caches."""

    def __init__(self, run_parent, inputs_root='/inputs'):
        if Path('/reference').exists():
            raise RuntimeError('Viewer must not mount raw UAS references')
        self.run_parent = Path(run_parent).resolve()
        self.run_root = self.run_parent/'run'
        self.inputs_root = Path(inputs_root)
        self.config, self.method_seal, self.method_seal_sha256 = verify_method_seal(self.run_root)
        if self.config.get('task_id') != TASK_ID:
            raise ValueError('Viewer is pinned to the completed source-candidate task')
        evaluation_root = self.run_root/'evaluation'
        receipt = _read(evaluation_root/'evaluation_receipt.json')
        if (receipt.get('method_seal_sha256') != self.method_seal_sha256
                or receipt.get('scientific_verdict') is not None
                or receipt.get('reference_accessed_only_after_all_method_verification') is not True):
            raise ValueError('Evaluation receipt is not bound to the sealed method')
        if not {'per_cell.json', 'summary.json'} <= set(receipt['output_sha256']):
            raise ValueError('Evaluation receipt lacks required viewer summaries')
        _verify_files(evaluation_root, receipt['output_sha256'])
        self.evaluation_summary = _read(evaluation_root/'summary.json')
        if self.evaluation_summary.get('method_seal_sha256') != self.method_seal_sha256:
            raise ValueError('Evaluation summary method provenance mismatch')
        evaluation_rows = _read(evaluation_root/'per_cell.json')
        self._regions = {}
        self._view_cache, self._depth_cache, self._pair_cache = OrderedDict(), OrderedDict(), OrderedDict()
        self._lock = threading.RLock()
        checked_images = {}
        for region, spec in self.config['regions'].items():
            native_path, views_path = (self.inputs_root/region/name for name in ('native.npz','views.json'))
            if sha(native_path) != spec['native_sha256'] or sha(views_path) != spec['views_sha256']:
                raise ValueError('Exact native/view input identity changed: ' + region)
            with np.load(native_path, allow_pickle=False) as archive:
                if any('uas' in k.lower() or 'reference' in k.lower() for k in archive.files):
                    raise ValueError('Viewer native package contains reference geometry')
                native = {k: archive[k] for k in archive.files}
            views = _read(views_path)['views']
            if len(views) != spec['view_count']:
                raise ValueError('Regional view count mismatch')
            root = self.run_root/region
            rows = _read(root/'candidates.json')
            observations = {r['cell_id']:r['observation'] for r in _read(root/'observations.json')}
            decisions = {r['cell_id']:r for r in _read(root/'decisions.json')}
            evaluated = {r['cell_id']:r for r in evaluation_rows if r['region']==region}
            cells = {r['cell_id']:r for r in rows}
            if len(cells) != len(rows) or any(set(cells) != set(m) for m in (observations,decisions,evaluated)):
                raise ValueError('Cell identity differs between frozen stages')
            with np.load(root/'membership.npz', allow_pickle=False) as archive:
                membership = {k:archive[k] for k in archive.files}
            ledger = {str(v['image_id']):v for v in _read(root/'rgb_ledger.json')}
            view_map = {str(v['image_id']):v for v in views}
            if len(view_map) != len(views) or set(ledger) != set(view_map):
                raise ValueError('Frozen RGB ledger/view IDs differ')
            for vid, view in view_map.items():
                record = ledger[vid]
                if any(record[k] != view[k] for k in ('name','sha256','width','height')):
                    raise ValueError('RGB ledger disagrees with view metadata')
                path = Path(view['path'])
                if not path.is_absolute() or path.name != view['name'] or Path(view['name']).name != view['name']:
                    raise ValueError('Invalid original image path')
                actual = checked_images.get(str(path))
                if actual is None:
                    actual = sha(path); checked_images[str(path)] = actual
                if actual != view['sha256']:
                    raise ValueError('Original RGB bytes changed: ' + str(path))
            for source in ('mvs','als'):
                xyz = native[source+'_xyz']
                if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
                    raise ValueError('Invalid native point coordinates')
                if (membership[source+'_cell'].shape != (len(xyz),)
                        or membership[source+'_inlier'].shape != (len(xyz),)):
                    raise ValueError('Native membership shape mismatch')
            self._regions[region] = dict(rows=rows,cells=cells,observations=observations,decisions=decisions,
                evaluation=evaluated,native=native,membership=membership,views=views,view_map=view_map,
                summary={name:_read(root/(name+'_summary.json')) for name in ('input','observation','decision')})
            self._regions[region]['summary']['evaluation'] = self.evaluation_summary['regions'][region]
        self.verified_image_count = len(checked_images)

    def _data(self, region):
        if region not in self._regions:
            raise KeyError('Unknown region: ' + str(region))
        return self._regions[region]

    def _cell(self, region, cid):
        data = self._data(region)
        if isinstance(cid, bool) or int(cid) != cid or int(cid) not in data['cells']:
            raise KeyError('Unknown cell: ' + str(cid))
        return data, data['cells'][int(cid)]

    @staticmethod
    def _view_public(region, view):
        return dict(id=view['image_id'],name=view['name'],width=view['width'],height=view['height'],
                    image_url=f"/images/{region}/{view['image_id']}")

    def manifest(self):
        return clean(dict(task_id=TASK_ID,scientific_verdict=None,method_seal_sha256=self.method_seal_sha256,
            verified_image_count=self.verified_image_count,regions=[dict(id=region,domain=self.config['regions'][region]['domain'],
                summary=data['summary'],default_cell_id=DEFAULT_CELLS[region] if DEFAULT_CELLS[region] in data['cells'] else min(data['cells']))
                for region,data in self._regions.items()]))

    def region(self, region):
        data=self._data(region);rows=[]
        for row in data['rows']:
            cid=row['cell_id'];obs=data['observations'][cid]
            item={k:row[k] for k in ('cell_id','ix','iy','x','y','bbox_xy','both_valid','height_difference_m','availability','candidates')}
            item.update(observation={**{k:obs['shared'][k] for k in ('common_scored_pair_count','distinct_view_count','disjoint_pair_count')},
                'status':obs['status'],'mvs_cost':obs['candidates']['mvs']['cost'],'als_cost':obs['candidates']['als']['cost']},
                decision=data['decisions'][cid],evaluation=data['evaluation'][cid])
            rows.append(item)
        return clean(dict(id=region,domain=self.config['regions'][region]['domain'],cells=rows,
                          views=[self._view_public(region,v) for v in data['views']]))

    def _point_payload(self, data, source, indices=None):
        if source not in ('mvs','als'):
            raise KeyError('Unknown native source')
        xyz=data['native'][source+'_xyz']
        if indices is None:
            indices=np.arange(len(xyz))
        native_count=len(indices)
        if native_count>DISPLAY_CAP:
            indices=indices[np.linspace(0,native_count-1,DISPLAY_CAP,dtype=int)]
        color=data['native'].get(source+'_rgb')
        rgb=color[indices] if color is not None else np.tile(np.array([225,138,38],np.uint8),(len(indices),1))
        return clean(dict(positions=xyz[indices].ravel(),colors=rgb.ravel(),native_count=native_count,
                          display_count=len(indices),native_row_indices=indices,
                          display_only=True,display_sampling='deterministic original-row subset; no coordinate averaging'))

    def points(self, region, source):
        return self._point_payload(self._data(region),source)

    def cell(self, region, cid):
        data,row=self._cell(region,cid);cid=row['cell_id']
        return clean(dict(region=region,cell_id=cid,candidate=row,observation=data['observations'][cid],
            decision=data['decisions'][cid],evaluation=data['evaluation'][cid],
            points={s:self._point_payload(data,s,np.flatnonzero(data['membership'][s+'_cell']==cid)) for s in ('mvs','als')}))

    def image_path(self, region, image_id):
        views=self._data(region)['view_map']
        key=str(image_id)
        if key not in views:
            raise KeyError('Image ID is absent from the exact regional RGB ledger')
        return Path(views[key]['path'])

    def _load_view(self, region, image_id):
        data=self._data(region);meta=data['view_map'][str(image_id)];key=(str(meta['path']),meta['sha256'])
        if key in self._view_cache:
            self._view_cache.move_to_end(key);return self._view_cache[key]
        gray=cv2.imread(str(self.image_path(region,image_id)),cv2.IMREAD_GRAYSCALE)
        if gray is None or gray.shape!=(meta['height'],meta['width']):
            raise ValueError('Original RGB dimensions changed')
        R,t=np.asarray(meta['R'],float),np.asarray(meta['t'],float)
        view=dict(id=meta['image_id'],name=meta['name'],width=meta['width'],height=meta['height'],R=R,t=t,
                  K=np.asarray(meta['K'],float),center=-R.T@t,gray=gray.astype(np.float32))
        return _remember(self._view_cache,key,view,8)

    def _depth(self, region, source, view):
        key=(region,source,str(view['id']))
        if key in self._depth_cache:
            self._depth_cache.move_to_end(key);return self._depth_cache[key]
        setting=self.config['self_visibility']
        result=self_depth_buffer(self._data(region)['native'][source+'_xyz'],view,setting['downsample'],setting['splat_radius'])
        return _remember(self._depth_cache,key,result,16)

    def _pairs(self, observation):
        sources={s:{r['pair_id']:r for r in observation['candidates'][s]['pairs']} for s in ('mvs','als')}
        result=[]
        for pair in observation['shared']['selected_pairs']:
            costs={s:sources[s].get(pair['pair_id'],{}).get('cost') for s in ('mvs','als')}
            result.append(dict(pair_id=pair['pair_id'],reference_id=pair['reference_id'],target_id=pair['target_id'],
                mvs_cost=costs['mvs'],als_cost=costs['als'],scored=all(_finite(v) for v in costs.values())))
        return result,sources

    def _replay(self, region, cid, pair, sources):
        key=(region,cid,pair['pair_id'])
        if key in self._pair_cache:
            self._pair_cache.move_to_end(key);return self._pair_cache[key]
        data,row=self._cell(region,cid);obs=data['observations'][cid];cfg=ScoringConfig(**obs['config'])
        views=[self._load_view(region,pair[k]) for k in ('reference_id','target_id')]
        prepared={}
        for source in ('mvs','als'):
            mask=(data['membership'][source+'_cell']==cid)&data['membership'][source+'_inlier']
            candidate=dict(row['candidates'][source],support_points=data['native'][source+'_xyz'][mask],
                context_depths={v['id']:self._depth(region,source,v) for v in views})
            prepared[source]=_prepare_candidate(candidate,cfg)
        centers=sources['mvs'][pair['pair_id']]['reference_pixel_centers']
        if centers!=sources['als'][pair['pair_id']]['reference_pixel_centers']:
            raise ValueError('Saved source candidates used different reference anchors')
        pixels=_patch_pixels(views[0],prepared,cfg,centers)
        reference=_sample_gray(pixels,views[0],cfg)
        warps={s:_warp(pixels,*views,prepared[s],cfg) for s in ('mvs','als')}
        common=warps['mvs']['valid']&warps['als']['valid'];costs={}
        for source in ('mvs','als'):
            values,_,_=_cost(reference,warps[source]['values'],common,cfg);costs[source]=values
            finite=values[np.isfinite(values)]
            recorded=sources[source][pair['pair_id']]['cost']
            if not len(finite) or not np.isclose(float(np.median(finite)),recorded,atol=1e-6,rtol=0):
                raise ValueError('Saved/replayed camera-pair cost mismatch: '+source)
            if len(finite)!=sources[source][pair['pair_id']]['common_patch_count']:
                raise ValueError('Saved/replayed valid patch count mismatch')
        valid=np.flatnonzero(np.isfinite(costs['mvs'])&np.isfinite(costs['als']))
        target_pixels={s:project(_intersect(pixels,views[0],prepared[s],0,cfg)[0],views[1])[0] for s in ('mvs','als')}
        return _remember(self._pair_cache,key,dict(cfg=cfg,views=views,pixels=pixels,reference=reference,warps=warps,
            common=common,costs=costs,valid=valid,target_pixels=target_pixels),12)

    def evidence(self, region, cid, pair_id=None, anchor=None):
        """Replay any saved scored pair; None chooses its most-supported anchor."""
        with self._lock:
            data,row=self._cell(region,cid);cid=row['cell_id'];obs=data['observations'][cid]
            pairs,sources=self._pairs(obs)
            base=dict(available=False,region=region,cell_id=cid,pairs=pairs,reproduced=False,
                      profile={s:obs['candidates'][s]['profile'] for s in ('mvs','als')},scientific_verdict=None)
            selected=next((p for p in pairs if p['scored']),None) if pair_id is None else next((p for p in pairs if p['pair_id']==pair_id),None)
            if selected is None:
                return clean(dict(base,reason='NO_SCORED_CAMERA_PAIR' if pair_id is None else 'UNKNOWN_SAVED_PAIR'))
            if not selected['scored']:
                return clean(dict(base,reason='SAVED_PAIR_HAS_NO_COMMON_PHOTOMETRIC_SCORE',pair_id=selected['pair_id']))
            replay=self._replay(region,cid,selected,sources)
            valid=replay['valid']
            if not len(valid):
                return clean(dict(base,reason='NO_VALID_ANCHOR',pair_id=selected['pair_id']))
            if anchor is None:
                chosen=int(valid[np.argmax(replay['common'][valid].sum(1))])
                selection='maximum common valid pixel count; ties first'
            elif isinstance(anchor,(int,np.integer)) and 0<=anchor<len(replay['pixels']):
                chosen=int(anchor);selection='explicit saved anchor index'
                if chosen not in valid:
                    return clean(dict(base,reason='ANCHOR_UNSCORED',pair_id=selected['pair_id'],anchor=chosen,
                                      anchor_count=len(replay['pixels']),anchor_indices_valid=valid))
            else:
                return clean(dict(base,reason='ANCHOR_OUT_OF_RANGE',pair_id=selected['pair_id'],anchor_count=len(replay['pixels']),anchor_indices_valid=valid))
            ref,target=replay['views']
            ref_public=self._view_public(region,dict(ref,image_id=ref['id']));target_public=self._view_public(region,dict(target,image_id=target['id']))
            ref_public['url']=ref_public.pop('image_url');target_public['url']=target_public.pop('image_url')
            ref_public['pixels']=replay['pixels'][chosen]
            target_public['pixels']={s:replay['target_pixels'][s][chosen] for s in ('mvs','als')}
            return clean(dict(base,available=True,reproduced=True,pair_id=selected['pair_id'],anchor=chosen,
                anchor_count=len(replay['pixels']),anchor_indices_valid=valid,anchor_selection=selection,
                reference=ref_public,target=target_public,
                patch=dict(width=replay['cfg'].patch_width,reference=replay['reference'][chosen].ravel(),
                    mvs=replay['warps']['mvs']['values'][chosen].ravel(),als=replay['warps']['als']['values'][chosen].ravel(),
                    mask=replay['common'][chosen].ravel(),costs={s:float(replay['costs'][s][chosen]) for s in ('mvs','als')},
                    common_pixel_count=int(replay['common'][chosen].sum())),
                reproduced_pair_costs={s:float(np.median(replay['costs'][s][np.isfinite(replay['costs'][s])])) for s in ('mvs','als')},
                reproduction_tolerance=1e-6,visibility_semantics='MODEL_SELF_VISIBILITY',
                evidence_status='Original source images and exact saved nominal masks; no new source decision'))
